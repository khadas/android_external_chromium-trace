# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import unittest

from tvcm import fake_fs


class FakeFSUnittest(unittest.TestCase):

  def testBasic(self):
    fs = fake_fs.FakeFS()
    fs.AddFile('/blah/x', 'foobar')
    with fs:
      assert os.path.exists(os.path.normpath('/blah/x'))
      self.assertEquals(
          'foobar',
          open(os.path.normpath('/blah/x'), 'r').read())

  def testWithableOpen(self):
    fs = fake_fs.FakeFS()
    fs.AddFile('/blah/x', 'foobar')
    with fs:
      with open(os.path.normpath('/blah/x'), 'r') as f:
        self.assertEquals('foobar', f.read())

  def testWalk(self):
    fs = fake_fs.FakeFS()
    fs.AddFile('/x/w2/w3/z3.txt', '')
    fs.AddFile('/x/w/z.txt', '')
    fs.AddFile('/x/y.txt', '')
    fs.AddFile('/a.txt', 'foobar')
    with fs:
      gen = os.walk(os.path.normpath('/'))
      r = gen.next()
      self.assertEquals((os.path.normpath('/'), ['x'], ['a.txt']), r)

      r = gen.next()
      self.assertEquals((os.path.normpath('/x'), ['w', 'w2'], ['y.txt']), r)

      r = gen.next()
      self.assertEquals((os.path.normpath('/x/w'), [], ['z.txt']), r)

      r = gen.next()
      self.assertEquals((os.path.normpath('/x/w2'), ['w3'], []), r)

      r = gen.next()
      self.assertEquals((os.path.normpath('/x/w2/w3'), [], ['z3.txt']), r)

      self.assertRaises(StopIteration, gen.next)
