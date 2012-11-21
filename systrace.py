#!/usr/bin/env python

# Copyright (c) 2011 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Android system-wide tracing utility.

This is a tool for capturing a trace that includes data from both userland and
the kernel.  It creates an HTML file for visualizing the trace.
"""

import errno, optparse, os, select, subprocess, sys, time, zlib

flattened_css_file = 'style.css'
flattened_js_file = 'script.js'

def add_adb_serial(command, serial):
  if serial != None:
    command.insert(1, serial)
    command.insert(1, '-s')

def main():
  usage = "Usage: %prog [options] [category1 [category2 ...]]"
  desc = "Example: %prog -b 32768 -t 15 gfx input view sched freq"
  parser = optparse.OptionParser(usage=usage, description=desc)
  parser.add_option('-o', dest='output_file', help='write HTML to FILE',
                    default='trace.html', metavar='FILE')
  parser.add_option('-t', '--time', dest='trace_time', type='int',
                    help='trace for N seconds', metavar='N')
  parser.add_option('-b', '--buf-size', dest='trace_buf_size', type='int',
                    help='use a trace buffer size of N KB', metavar='N')
  parser.add_option('-k', '--ktrace', dest='kfuncs', action='store',
                    help='specify a comma-separated list of kernel functions to trace')
  parser.add_option('-l', '--list-categories', dest='list_categories', default=False,
                    action='store_true', help='list the available categories and exit')
  parser.add_option('-a', '--app', dest='app_name', default=None, type='string',
                    action='store', help='enable application-level tracing for comma-separated ' +
                    'list of app cmdlines')

  parser.add_option('--link-assets', dest='link_assets', default=False,
                    action='store_true', help='link to original CSS or JS resources '
                    'instead of embedding them')
  parser.add_option('--from-file', dest='from_file', action='store',
                    help='read the trace from a file (compressed) rather than running a live trace')
  parser.add_option('--asset-dir', dest='asset_dir', default='trace-viewer',
                    type='string', help='')
  parser.add_option('-e', '--serial', dest='device_serial', type='string',
                    help='adb device serial number')

  options, args = parser.parse_args()

  if options.list_categories:
    atrace_args = ['adb', 'shell', 'atrace', '--list_categories']
    expect_trace = False
  elif options.from_file is not None:
    atrace_args = ['cat', options.from_file]
    expect_trace = True
  else:
    atrace_args = ['adb', 'shell', 'atrace', '-z']
    expect_trace = True

    if options.trace_time is not None:
      if options.trace_time > 0:
        atrace_args.extend(['-t', str(options.trace_time)])
      else:
        parser.error('the trace time must be a positive number')

    if options.trace_buf_size is not None:
      if options.trace_buf_size > 0:
        atrace_args.extend(['-b', str(options.trace_buf_size)])
      else:
        parser.error('the trace buffer size must be a positive number')

    if options.app_name is not None:
      atrace_args.extend(['-a', options.app_name])

    if options.kfuncs is not None:
      atrace_args.extend(['-k', options.kfuncs])

    atrace_args.extend(args)

  if atrace_args[0] == 'adb':
    add_adb_serial(atrace_args, options.device_serial)

  script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))

  if options.link_assets:
    src_dir = os.path.join(script_dir, options.asset_dir, 'src')
    build_dir = os.path.join(script_dir, options.asset_dir, 'build')

    js_files, js_flattenizer, css_files = get_assets(src_dir, build_dir)

    css = '\n'.join(linked_css_tag % (os.path.join(src_dir, f)) for f in css_files)
    js = '<script language="javascript">\n%s</script>\n' % js_flattenizer
    js += '\n'.join(linked_js_tag % (os.path.join(src_dir, f)) for f in js_files)
  else:
    css_filename = os.path.join(script_dir, flattened_css_file)
    js_filename = os.path.join(script_dir, flattened_js_file)
    css = compiled_css_tag % (open(css_filename).read())
    js = compiled_js_tag % (open(js_filename).read())

  html_filename = options.output_file

  adb = subprocess.Popen(atrace_args, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)

  result = None
  data = []

  # Read the text portion of the output and watch for the 'TRACE:' marker that
  # indicates the start of the trace data.
  while result is None:
    ready = select.select([adb.stdout, adb.stderr], [], [adb.stdout, adb.stderr])
    if adb.stderr in ready[0]:
      err = os.read(adb.stderr.fileno(), 4096)
      sys.stderr.write(err)
      sys.stderr.flush()
    if adb.stdout in ready[0]:
      out = os.read(adb.stdout.fileno(), 4096)
      parts = out.split('\nTRACE:', 1)

      txt = parts[0].replace('\r', '')
      if len(parts) == 2:
        # The '\nTRACE:' match stole the last newline from the text, so add it
        # back here.
        txt += '\n'
      sys.stdout.write(txt)
      sys.stdout.flush()

      if len(parts) == 2:
        data.append(parts[1])
        sys.stdout.write("downloading trace...")
        sys.stdout.flush()
        break

    result = adb.poll()

  # Read and buffer the data portion of the output.
  while result is None:
    ready = select.select([adb.stdout, adb.stderr], [], [adb.stdout, adb.stderr])
    if adb.stderr in ready[0]:
      err = os.read(adb.stderr.fileno(), 4096)
      sys.stderr.write(err)
      sys.stderr.flush()
    if adb.stdout in ready[0]:
      out = os.read(adb.stdout.fileno(), 4096)
      data.append(out)

    result = adb.poll()

  if result == 0:
    if expect_trace:
      data = ''.join(data)

      # Collapse CRLFs that are added by adb shell.
      if data.startswith('\r\n'):
        data = data.replace('\r\n', '\n')

      # Skip the initial newline.
      data = data[1:]

      if not data:
        print >> sys.stderr, ('No data was captured.  Output file was not ' +
          'written.')
        sys.exit(1)
      else:
        # Indicate to the user that the data download is complete.
        print " done\n"

      html_file = open(html_filename, 'w')
      html_file.write(html_prefix % (css, js))

      size = 4096
      dec = zlib.decompressobj()
      for chunk in (data[i:i+size] for i in xrange(0, len(data), size)):
        decoded_chunk = dec.decompress(chunk)
        html_chunk = decoded_chunk.replace('\n', '\\n\\\n')
        html_file.write(html_chunk)

      html_out = dec.flush().replace('\n', '\\n\\\n')
      html_file.write(html_out)
      html_file.write(html_suffix)
      html_file.close()
      print "\n    wrote file://%s/%s\n" % (os.getcwd(), options.output_file)

  else: # i.e. result != 0
    print >> sys.stderr, 'adb returned error code %d' % result
    sys.exit(1)

def get_assets(src_dir, build_dir):
  sys.path.append(build_dir)
  gen = __import__('generate_standalone_timeline_view', {}, {})
  parse_deps = __import__('parse_deps', {}, {})
  filenames = gen._get_input_filenames()
  load_sequence = parse_deps.calc_load_sequence(filenames, src_dir)

  js_files = []
  js_flattenizer = "window.FLATTENED = {};\n"
  css_files = []

  for module in load_sequence:
    js_files.append(os.path.relpath(module.filename, src_dir))
    js_flattenizer += "window.FLATTENED['%s'] = true;\n" % module.name
    for style_sheet in module.style_sheets:
      css_files.append(os.path.relpath(style_sheet.filename, src_dir))

  sys.path.pop()

  return (js_files, js_flattenizer, css_files)

html_prefix = """<!DOCTYPE HTML>
<html>
<head i18n-values="dir:textdirection;">
<meta charset="utf-8"/>
<title>Android System Trace</title>
%s
%s
<script language="javascript">
document.addEventListener('DOMContentLoaded', function() {
  if (!linuxPerfData)
    return;

  var m = new tracing.Model(linuxPerfData);
  var timelineViewEl = document.querySelector('.view');
  tracing.ui.decorate(timelineViewEl, tracing.TimelineView);
  timelineViewEl.model = m;
  timelineViewEl.tabIndex = 1;
  timelineViewEl.timeline.focusElement = timelineViewEl;
});
</script>
<style>
  .view {
    overflow: hidden;
    position: absolute;
    top: 0;
    bottom: 0;
    left: 0;
    right: 0;
  }
</style>
</head>
<body>
  <div class="view">
  </div>
<!-- BEGIN TRACE -->
  <script>
  var linuxPerfData = "\\
"""

html_suffix = """\\n";
  </script>
<!-- END TRACE -->
</body>
</html>
"""

compiled_css_tag = """<style type="text/css">%s</style>"""
compiled_js_tag = """<script language="javascript">%s</script>"""

linked_css_tag = """<link rel="stylesheet" href="%s"></link>"""
linked_js_tag = """<script language="javascript" src="%s"></script>"""

if __name__ == '__main__':
  main()
