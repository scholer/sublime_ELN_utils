#!/usr/bin/env python
# -*- coding: utf-8 -*-
##    Copyright 2015 Rasmus Scholer Sorensen, rasmusscholer@gmail.com
##
##    This program is free software: you can redistribute it and/or modify
##    it under the terms of the GNU General Public License as published by
##    the Free Software Foundation, either version 3 of the License, or
##    (at your option) any later version.
##
##    This program is distributed in the hope that it will be useful,
##    but WITHOUT ANY WARRANTY; without even the implied warranty of
##    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
##    GNU General Public License for more details.
##
##    You should have received a copy of the GNU General Public License
##    along with this program.  If not, see <http://www.gnu.org/licenses/>.

# pylint: disable=C0103,W0232,R0903,R0201

"""
Sublime ELN utils - Sublime plugin with various utilities
that makes using Sublime Text as a Electronic Laboratory Notebook
a bit easier.


"""

from __future__ import print_function
from datetime import datetime
import sublime
import sublime_plugin


rseq = r = lambda seq: "".join(reversed(seq))
wc_maps = {
    'dna': dict(zip("5'-ATGC-3'", "3'-TACG-5'")),
    'rna': dict(zip("5'-AUGC-3'", "3'-UACG-5'")),
    }
#compl = lambda seq, wc_map: "".join(wc_maps[wc_map].get(b, b) for b in seq.upper())
#rcompl = lambda seq: "".join(reversed(compl(seq)))
def compl(seq, wc_map="dna"):
    return "".join(wc_maps[wc_map].get(b, b) for b in seq.upper())
def rcompl(seq, wc_map="dna"):
    return "".join(reversed(compl(seq)))
dna_filter = d = lambda seq: "".join(b for b in seq.upper() if b in "ATCGU")


class ElnInsertSnippetCommand(sublime_plugin.TextCommand):
    """
    Command string: eln_insert_snippet
    When run, insert text at position in the view.
    If position is None, insert at current position.
    Other commonly-used shortcuts are:
        cursor_position = self.view.sel()[0].begin()
        end_of_file = self.view.size()
        start_of_file = 0

    Note: You can also use Sublime's own snippets feature for simple snippets,
    c.f. http://docs.sublimetext.info/en/latest/extensibility/snippets.html
    """
    def run(self, edit, snippet, position=None):
        """ TextCommand entry point, edit token is provided by Sublime. """
        if position is None:
            # Note: Probably better to use built-in command, "insert":
            # { "keys": ["enter"], "command": "insert", "args": {"characters": "\n"} }
            position = self.view.sel()[0].begin()
            #position = self.view.size()

        snippets = {'journal_date_header': "'''Journal, {date:%Y-%m-%d}:'''\n * "}
        text = snippets[snippet]
        text = text.format(date=datetime.now())
        self.view.insert(edit, position, text)
        print("Inserted %s chars at pos %s" % (len(text), position))


class ElnSequenceTransformCommand(sublime_plugin.TextCommand):
    """
    Command string: eln_sequence_transform
    Commonly-used shortcuts are:
        cursor_position = self.view.sel()[0].begin()
        end_of_file = self.view.size()
        start_of_file = 0
    """

    def run(self, edit, complement=True, reverse=False, dna_only=False, replace=True, wc_map="dna"):
        """
        TextCommand entry point, edit token is provided by Sublime.
        - reverse: If true, reverse the complement.
        - dna_only: Filter input to only include DNA bases.
        - replace: replace selection. If False, the complement sequences will be appended to buffer.
        """
        selections = self.view.sel()
        for selection in selections:
            if selection.empty():
                continue
            seq = self.view.substr(selection)
            if dna_only:
                seq = dna_filter(seq)
            if complement:
                text = rcompl(seq, wc_map) if reverse else compl(seq, wc_map)
            elif reverse:
                text = rseq(seq)
            if reverse:
                # Last step in "5'-ATGC-3'" -> "'5-GCAT-'3" -> "5'-GCAT-3'"
                text = text.replace("'5-", "5'-").replace("-'3", "-3'")
            if replace:
                # Replace selection with new sequence
                self.view.replace(edit, selection, text)
                pos = selection.begin()
            else:
                # Append new sequence to end of view:
                pos = self.view.size()
                self.view.insert(edit, pos, text)
            print("Inserted %s chars at pos %s" % (len(text), pos))


class ElnSequenceStats(sublime_plugin.TextCommand):
    """
    Command string: eln_sequence_stats
    Commonly-used shortcuts are:
        cursor_position = self.view.sel()[0].begin()
        end_of_file = self.view.size()
        start_of_file = 0
    """

    def run(self, edit, dna_only=False, wc_map="dna"):
        """
        TextCommand entry point, edit token is provided by Sublime.
        - reverse: If true, reverse the complement.
        - dna_only: Filter input to only include DNA bases.
        - replace: replace selection. If False, the complement sequences will be appended to buffer.
        """
        selections = self.view.sel()
        print("\n" + "-"*20, "ELN: Sequence stats", "-"*20)
        for selection in selections:
            if selection.empty():
                continue
            seq = self.view.substr(selection)
            if dna_only:
                seq = dna_filter(seq)
            print("\nSeq = %s:" % seq)
            counts = {k: sum(1 for b in seq if b == k) for k in "ATGC"}
            gc = sum(counts[k] for k in "GC")
            tot = sum(counts.values())
            s = "GC content: {:0.02f} ({}/{})".format(gc/tot, gc, tot)
            print("*", s)
            sublime.status_message(s)
        print("-"*80)
