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

# pylint: disable=C0103,W0232,R0903,R0201,W0201,E1101

"""
Sublime ELN utils - Sublime plugin with various utilities
that makes using Sublime Text as a Electronic Laboratory Notebook
a bit easier.


"""

from __future__ import print_function
import os
import glob
import re
from datetime import datetime
import logging
logger = logging.getLogger(__name__)
import sublime
import sublime_plugin


SETTINGS_NAME = 'eln_utils.sublime-settings'
snippets = {'journal_date_header': "'''Journal, {date:%Y-%m-%d}:'''",
            'journal_daily_start': "'''Journal, {date:%Y-%m-%d}:'''\n* {date:%H:%M} > ",
            'journal_timestamp': "* {date:%H:%M} > ",
           }


rseq = r = lambda seq: "".join(reversed(seq))
wc_maps = {
    'dna': dict(zip("5'-ATGC-3'", "3'-TACG-5'")),
    'rna': dict(zip("5'-AUGC-3'", "3'-UACG-5'")),
    }
#compl = lambda seq, wc_map: "".join(wc_maps[wc_map].get(b, b) for b in seq.upper())
#rcompl = lambda seq: "".join(reversed(compl(seq)))
def compl(seq, wc_map="dna"):
    """ Return complement of seq (not reversed). """
    return "".join(wc_maps[wc_map].get(b, b) for b in seq.upper())
def rcompl(seq, wc_map="dna"):
    """ Return complement of seq, reversed. """
    return "".join(reversed(compl(seq, wc_map)))
dna_filter = d = lambda seq: "".join(b for b in seq.upper() if b in "ATCGU")


def get_setting(key, default_value=None):
    """
    Returns setting for key <key>, defaulting to default_value if not present (default: None)
    Note that the returned object seems to be a copy;
    changes, even to mutable entries, cannot simply be persisted with sublime.save_settings.
    You have to keep a reference to the original settings object and make changes to this.
    """
    settings = sublime.load_settings(SETTINGS_NAME)
    return settings.get(key, default_value)



class ElnMergeJournalNotesCommand(sublime_plugin.TextCommand):
    """
    Command string: eln_merge_journal_notes
    Will move text from a journal notes file to the current cursor position.
    """
    def run(self, edit, position=None, move=True, add_journal_header=True,
            paragraphs_to_bullet=True, add_timestamp=True):
        """ TextCommand entry point, edit token is provided by Sublime. """
        if position is None:
            position = self.view.sel()[0].begin()
        if position == -1:
            position = self.view.size() # End of file
        self.position = position
        self.move = move
        self.add_journal_header = add_journal_header
        self.edit_token = edit
        self.paragraphs_to_bullet = paragraphs_to_bullet
        self.add_timestamp = add_timestamp

        # find files
        settings = sublime.load_settings(SETTINGS_NAME)
        note_dirs = settings.get('external_journal_dirs')
        print("note_dirs:", note_dirs)
        view_filename = self.view.file_name()
        if not note_dirs:
            print("Setting key 'external_journal_dirs' not found, using current file dir...")
            if not view_filename:
                print("Current view is not saved; aborting...")
            note_dirs = [os.path.dirname(view_filename)]
        journal_notes_pattern = settings.get('journal_notes_pattern', '*')
        min_file_size = settings.get('min_file_size', 10)
        self.filepaths = [os.path.join(dirpath, filename) for dirpath in note_dirs
                          for filename in glob.glob(os.path.join(dirpath, journal_notes_pattern))]
        self.filepaths = [fp for fp in self.filepaths
                          if os.path.isfile(fp)
                          and os.path.getsize(fp) >= min_file_size]
        self.filebasenames = [os.path.basename(pathname) for pathname in self.filepaths]
        print(self.filebasenames)
        if not self.filepaths:
            msg = "No files larger than {} bytes found in {}".format(min_file_size, note_dirs)
            print(msg)
            sublime.status_message(msg)
            return

        # select best file candidate:
        # find file that matches current file the most:
        # Just add view_filename to a combined list, sort the list, and see what index it is at.
        # Then when you use that index against self.filebasenames, it will select a file that is close.
        combined = [view_filename] + self.filebasenames
        combined.sort()
        selected_index = combined.index(view_filename)
        # Or find files with same expid:
        view_filename_pat = settings.get('view_filename_pat')
        view_regex_match = re.match(view_filename_pat, os.path.basename(view_filename)) \
                           if view_filename_pat else 0
        if view_regex_match is None:
            print(view_filename_pat, "did not match view file basename:", os.path.basename(view_filename))
        notes_filename_pat = settings.get('notes_filename_pat')
        notes_filename_keys = settings.get('notes_filename_keys')
        if view_regex_match and notes_filename_pat and notes_filename_keys:
            notes_filename_regex = re.compile(notes_filename_pat)
            notes_regex_matches = [notes_filename_regex.match(fn) for fn in self.filebasenames]
            notes_all_keys = [all(match.group(key) == view_regex_match.group(key)
                                  for key in notes_filename_keys) if match else 0
                              for match in notes_regex_matches]
            try:
                # Use the index for the first entry that yields a match in the list above:
                selected_index = notes_all_keys.index(True)
            except ValueError:
                print("notes_filename_keys:", notes_filename_keys,
                      "does not match any filenames. Using closest alphabetic match.")
                print("notes_all_keys:", notes_all_keys)
                print("notes_filename_regex:", notes_filename_regex)
                print("notes_regex_matches:", notes_regex_matches)
                print("notes_regex_matches groupdicts:", [m.groupdict() if m else None for m in notes_regex_matches])
                print([[(match.group(key), view_regex_match.group(key)) for key in notes_filename_keys]
                       if match else 0
                       for match in notes_regex_matches])
                # Perhaps fall back to the last selected file, if it is present in the list:
                last_selected = settings.get("last_external_journal")
                if last_selected in self.filebasenames:
                    selected_index = self.filebasenames.index(last_selected)

        # Display quick panel allowing the user to select the file:
        self.view.window().show_quick_panel(self.filebasenames, self.on_file_selected, selected_index=selected_index)


    def on_file_selected(self, index):
        """
        Called after user has selected the file to move note from.
        If quick panel was cancelled then index=-1.
        """
        if index < 0:
            print("Select journal file cancelled, index =", index)
            return
        self.filename = self.filepaths[index]
        print("Selected file:", self.filename)
        settings = sublime.load_settings(SETTINGS_NAME)
        settings.set("last_external_journal", self.filename)
        sublime.save_settings(SETTINGS_NAME)

        # read file:
        with open(self.filename) as fp:
            content = fp.read()
        if len(content) == 0:
            print("File does not contain any content:", content)
        # reformat paragraphs to bullet point:
        timestamp = snippets["journal_timestamp"].format(date=datetime.now()) if self.add_timestamp \
                    else ("* " if self.paragraphs_to_bullet else "")
        if self.paragraphs_to_bullet:
            content = "\n".join(timestamp + line for line in content.strip().split("\n\n"))
        elif self.add_timestamp:
            content = timestamp + content

        # Add journal header:
        if self.add_journal_header:
            header = snippets['journal_date_header'].format(date=datetime.now())
            #self.view.insert(edit_token, position, header)
            content = "\n".join([header, content])

        # Remove content from origin file:
        if self.move:
            with open(self.filename, 'w') as fp:
                fp.write("\n")
            print("Removed content from", self.filename)

        # Insert content:
        # self.view.insert(self.edit_token, self.position, content)        # Does edit tokens expire fast?
        # ValueError: Edit objects may not be used after the TextCommand's run method has returned
        # print("Inserted %s chars at pos %s" % (len(content), self.position))
        self.view.run_command("eln_insert_text", {"text": content, "position": self.position})
        sublime.status_message("Moved notes from {} to current cursor position.".format(self.filename))



class ElnInsertTextCommand(sublime_plugin.TextCommand):
    """
    Command string: eln_insert_text
    When run, insert text at position in the view.
    If position is None, insert at current position.
    If position is -1, insert at end of document.
    """
    def run(self, edit, text, position=None):
        """ TextCommand entry point, edit token is provided by Sublime. """
        if position is None:
            position = self.view.sel()[0].begin()
        if position == -1:
            position = self.view.size() # End of file

        self.view.insert(edit, position, text)
        print("Inserted %s chars at pos %s" % (len(text), position))




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

        # If <snippet> is not a key in the standard snippets dict, assume it is usable as-is:
        text = snippets.get(snippet, snippet)
        text = text.format(date=datetime.now())
        self.view.insert(edit, position, text)
        print("Inserted %s chars at pos %s" % (len(text), position))






############## DNA/RNA SEQUENCE UTILITIES ###########################



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
