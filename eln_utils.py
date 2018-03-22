#!/usr/bin/env python
# -*- coding: utf-8 -*-
#    Copyright 2015-2018 Rasmus Scholer Sorensen, rasmusscholer@gmail.com
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

# pylintx: disable=C0103,W0232,R0903,R0201,W0201,E1101

"""
Sublime ELN utils - Sublime plugin with various utilities
that makes using Sublime Text as a Electronic Laboratory Notebook
a bit easier.


"""

from __future__ import print_function
import os
import glob
import re
from datetime import date, datetime
import urllib.parse
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


def compl(seq, wc_map="dna"):
    """ Return complement of seq (not reversed). """
    return "".join(wc_maps[wc_map].get(b, b) for b in seq.upper())


def rcompl(seq, wc_map="dna"):
    """ Return complement of seq, reversed. """
    return "".join(reversed(compl(seq, wc_map)))


def dna_filter(seq):
    return "".join(b for b in seq.upper() if b in "ATCGU")


def get_settings():
    return sublime.load_settings(SETTINGS_NAME)


def get_setting(key, default_value=None):
    """
    Returns setting for key <key>, defaulting to default_value if not present (default: None)
    Note that the returned object seems to be a copy;
    changes, even to mutable entries, cannot simply be persisted with sublime.save_settings.
    You have to keep a reference to the original settings object and make changes to this.
    """
    settings = sublime.load_settings(SETTINGS_NAME)
    return settings.get(key, default_value)


#
# ELN Text commands:
# ------------------


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


class ElnCreateNewExperimentCommand(sublime_plugin.WindowCommand):
    """
    Command string: eln_create_new_experiment
    Create a new experiment:
    - exp folder, if mediawiker_experiments_basedir is specified.
    - new wiki page (in new buffer), if mediawiker_experiments_title_fmt is boolean true.
    - load buffer with template, if mediawiker_experiments_template
    --- and fill in template argument, as specified by mediawiker_experiments_template_args
    - Done: Create link to the new experiment page and append it to experiments_overview_page.
    - TODO: Move this command to ELN_Utils package.
    - Done: Option to save view buffer to file.
    - Done: Option to enable auto_save
    This is a window command, since we might not have any views open when it is invoked.

    Question: Does Sublime wait for window commands to finish, or are they dispatched to run
    asynchronously in a separate thread? ST waits for one command to finish before a new is invoked.
    In other words: *Commands cannot be used as functions*. That makes ST plugin development a bit convoluted.
    It is generally best to avoid any "run_command" calls, until the end of any methods/commands.

    """

    # def __init__(self):
    #     self.expid = None
    #     self.titledesc = None
    #     self.pagetitle = None
    #     self.bigcomment = None
    #     self.exp_buffer_text = None
    #     self.view = None
    #     sublime_plugin.WindowCommand.__init__(self)

    def run(self, expid=None, titledesc=None):
        self.expid = expid
        self.titledesc = titledesc
        self.exp_buffer_text = ""

        if self.expid is not None:
            self.expid_received(self.expid)
        else:
            # Start input chain:
            self.window.show_input_panel('Experiment ID:', '', self.expid_received, None, None)

    def expid_received(self, expid):
        """ Saves expid input and asks the user for titledesc. """
        self.expid = expid.strip()  # strip leading/trailing whitespace; empty string is OK.
        if self.titledesc is not None:
            self.titledesc_received(self.titledesc)
        else:
            self.window.show_input_panel('Exp title desc:', '', self.titledesc_received, None, None)

    def titledesc_received(self, titledesc):
        """ Saves titledesc input and asks the user for bigcomment text. """
        self.titledesc = titledesc.strip()  # strip leading/trailing whitespace; empty string is OK.
        # self.window.show_input_panel('Big page comment:', self.expid, self.bigcomment_received, None, None)
        self.done_collecting_variables()

    def bigcomment_received(self, bigcomment):
        """ Saves bigcomment input and invokes on_done. """
        self.bigcomment = bigcomment
        self.done_collecting_variables()

    def done_collecting_variables(self, dummy=None):
        """
        Called when all user input have been collected.
        Settings:
            'eln_experiments_basedir'
            'eln_experiments_title_fmt'
            'eln_experiments_filename_fmt'
            'eln_experiments_filename_quote'
            'eln_experiments_filename_quote_safe'
            'eln_experiments_foldername_fmt'
            'eln_experiments_template'
            'eln_experiments_template_subst_mode'
            'eln_experiments_template_kwargs'
            # 'eln_experiments_overview_page'
            'eln_experiments_save_to_file'
            'eln_experiments_enable_autosave'
        """
        print("\nCreating new experiment (expid=%s, titledesc=%s..." % (self.expid, self.titledesc))
        # Ways to format a date/datetime as string: startdate.strftime("%Y-%m-%d"), or "{:%Y-%m-%d}".format(startdate)

        # Non-attribute settings:
        startdate = date.today().isoformat()    # datetime.now()
        # The base directory where the user stores his experiments, e.g. /home/me/documents/experiments/
        settings = get_settings()
        exp_basedir = settings.get('eln_experiments_basedir')
        if exp_basedir is None:
            raise ValueError("'eln_experiments_basedir' must be defined in your configuration, aborting.")
        if exp_basedir:
            exp_basedir = os.path.abspath(os.path.expanduser(exp_basedir))
        # title format, e.g. "MyExperiments/{expid} {titledesc}". If not set, no new buffer is created.
        title_fmt = settings.get('eln_experiments_title_fmt', '{expid} {titledesc}')
        filename_fmt = settings.get('eln_experiments_filename_fmt', '{expid}.md')
        # quoting filename. 'quote' is for url paths, 'quote_plus' is for form data (uses '+' for spaces)
        filename_quote = settings.get('eln_experiments_filename_quote', None)  # None, 'quote', or 'quote_plus'
        filename_quote_safe = settings.get('eln_experiments_filename_quote_safe', '')  # don't touch these chars
        # How to format the folder, e.g. "{expid} {titledesc}"
        # If exp_foldername_fmt is not specified, use title_fmt - remove any '/' and whatever is before it
        foldername_fmt = settings.get('eln_experiments_foldername_fmt', (title_fmt or '').split('/')[-1])
        # Template settings:
        template = settings.get('eln_experiments_template')
        if template is None:
            print("Note: 'eln_experiments_template' is not specified in config.")
        if template and template.startswith("~"):
            template = os.path.expanduser(template)
        # template parameters substitution mode. Can be any of 'python-fmt', 'python-%' or 'mediawiki'.
        template_subst_mode = settings.get('eln_experiments_template_subst_mode', 'python-fmt') or 'python-fmt'
        # Constant args to feed to the template (Mostly for shared templates).
        template_kwargs = settings.get('eln_experiments_template_kwargs', {}) or {}
        # If save_to_file is True, the view/buffer is saved locally immediately upon creation:
        # Experiments overview page: A file/page that lists (and links) to all experiments.
        experiments_overview_page = settings.get('eln_experiments_overview_page')
        if experiments_overview_page and experiments_overview_page[0] == '~':
            experiments_overview_page = os.path.expanduser(experiments_overview_page)
        save_to_file = settings.get('eln_experiments_save_to_file', True)
        # Enable auto save. Requires auto-save plugin. github.com/scholer/auto-save
        enable_autosave = settings.get('eln_experiments_enable_autosave', False)

        if not any((self.expid, self.titledesc)):
            # If both expid and exp_title are empty, just abort:
            print("expid and titledesc are both empty, aborting...")
            return

        # 1. Make experiment folder, if appropriate:
        foldername = folderpath = None
        if exp_basedir and foldername_fmt:
            exp_basedir = exp_basedir.strip()
            if os.path.isdir(exp_basedir):
                foldername = foldername_fmt.format(expid=self.expid, titledesc=self.titledesc).strip()
                folderpath = os.path.join(exp_basedir, foldername)
                if os.path.isdir(folderpath):
                    msg = "NOTICE: The folderpath for the new experiment already exists: %s" % folderpath
                else:
                    try:
                        os.mkdir(folderpath)
                        msg = "OK: Created new experiment directory: %s" % (folderpath,)
                    except FileExistsError:
                        msg = "ERROR: New exp directory already exists: %s" % (folderpath,)
                    except (WindowsError, OSError, IOError) as e:
                        msg = "ERROR creating new exp directory '%s' :: %s" % (folderpath, repr(e))
            else:
                # We are not creating a new folder for the experiment because basedir doesn't exists:
                msg = "ERROR: Configured experiment base dir does not exists: %s" % (exp_basedir,)
            print(msg)
            sublime.status_message(msg)
        else:
            print("WARNING: exp_basedir or foldername_fmt not defined: %s, %s" % (exp_basedir, foldername_fmt))

        # 2. Make new view, if title_fmt is specified:
        self.pagetitle = title_fmt.format(expid=self.expid, titledesc=self.titledesc)
        self.view = exp_view = sublime.active_window().new_file() # Make a new file/buffer/view
        self.window.focus_view(exp_view)  # exp_view is now the window's active_view
        view_default_dir = folderpath
        filename = filename_fmt.format(title=self.pagetitle, expid=self.expid, titledesc=self.titledesc)
        if filename_quote:
            if filename_quote == 'quote_plus':
                filename = urllib.parse.quote_plus(filename, safe=filename_quote_safe)
            elif filename_quote == 'quote':
                filename = urllib.parse.quote(filename, safe=filename_quote_safe)
        if view_default_dir:
            view_default_dir = os.path.expanduser(view_default_dir)
            print("Setting view's default dir to:", view_default_dir)
            exp_view.settings().set('default_dir', view_default_dir) # Update the view's working dir.
        exp_view.set_name(filename)
        filepath = os.path.join(folderpath, filename)
        # Manually set the syntax file to use (if the view does not have a file extension)
        # self.view.set_syntax_file('Packages/Mediawiker/Mediawiki.tmLanguage')

        # 3. Create big comment text:
        # if self.bigcomment:
        #     exp_figlet_comment = get_figlet_text(self.bigcomment) # Makes the big figlet text
        #     # Adjusts the figlet to produce a comment and add it to the exp_buffer_text:
        #     self.exp_buffer_text += adjust_figlet_comment(exp_figlet_comment, foldername or self.bigcomment)

        # 4. Generate template :
        if template:
            # Load the template: #
            print("Using template:", template)
            try:
                # Open user configured local template file:
                with open(template) as fd:
                    template_content = fd.read()
                print(" - Template loaded from disk; length:", len(template_content))
            except FileNotFoundError as exc:
                print("ERROR: Could not open template file:", template, "(%s)" % exc)
                return

            # Perform template variable substitution:
            # Update kwargs with user input and today's date:
            template_kwargs.update({
                'expid': self.expid, 'titledesc': self.titledesc, 'title': self.pagetitle,
                'filename': filename, 'foldername': foldername, 'filepath': filepath, 'folderpath': folderpath,
                'startdate': startdate, 'date': startdate
            })
            if template_subst_mode == 'python-fmt':
                # template_kwargs must be dict/mapping: (template_args_order no longer supported)
                try:
                    template_content = template_content.format(**template_kwargs)
                except KeyError as exc:
                    print("%s: Unknown template variable %s" % (exc.__class__.__name__, exc))
                    sublime.status_message("ERROR: Unrecognized variable name in template: %s" % (exc,))
                    raise exc
            elif template_subst_mode == 'python-%':
                # "%s" string interpolation: template_vars must be tuple or dict (both will work):
                template_content = template_content % template_kwargs
            else:
                print("Unrecognized template_subst_mode '%s'" % (template_subst_mode,))

            # Add template to buffer text string:
            # self.exp_buffer_text = "".join(text.strip() for text in (self.exp_buffer_text, template_content))
            self.exp_buffer_text += template_content

        else:
            print('No template specified (settings key "eln_experiments_template").')

        # 6. Append self.exp_buffer_text to the view:
        exp_view.run_command('eln_insert_text', {'position': exp_view.size(), 'text': self.exp_buffer_text})

        # 7. Add a link to experiments_overview_page (local file):
        # if experiments_overview_page:
        #     # Generate a link to this experiment:
        #     link_fmt = mw.get_setting('eln_experiments_overview_link_fmt', "\n* [[{}]]")
        #     if self.pagetitle:
        #         link_text = link_fmt.format(self.pagetitle)
        #     else:
        #         # Add a link to the current buffer's title, assuming the experiment header is the same as foldername
        #         link = "{}#{}".format(mw.get_title(), foldername.replace(' ', '_'))
        #         link_text = link_fmt.format(link)
        #
        #     # Insert link on experiments_overview_page. Currently, this must be a local file.
        #     # (We just edit the file on disk and let ST pick up the change if the file is opened in any view.)
        #     if os.path.isfile(experiments_overview_page):
        #         print("Adding link '%s' to file '%s'" % (link_text, experiments_overview_page))
        #         # We have a local file, append link:
        #         with open(experiments_overview_page, 'a') as fd:
        #             # In python3, there is a bigger difference between binary 'b' mode and normal (text) mode.
        #             # Do not open in binary 'b' mode when writing/appending strings. It is not supported in python 3.
        #             # If you want to write strings to files opened in binary mode, you have to cast the string to bytes / encode it:
        #             # >>> fd.write(bytes(mystring, 'UTF-8')) *or* fd.write(mystring.encode('UTF-8'))
        #             fd.write(link_text) # The format should include newline if desired.
        #         print("Appended %s chars to file '%s" % (len(link_text), experiments_overview_page))
        #     else:
        #         # User probably specified a page on the wiki. (This is not yet supported.)
        #         # Even if this is a page on the wiki, you should check whether that page is already opened in Sublime.
        #         ## TODO: Implement specifying experiments_overview_page from server.
        #         print("Using experiment_overview_page from the server is not yet supported.")

        print("ElnCreateNewExperimentCommand completed!\n")
        if save_to_file:
            self.window.run_command("save")
        if enable_autosave:
            self.window.run_command("auto_save", args={"enable": True})


#
#
#
# DNA/RNA SEQUENCE UTILITIES:
# ---------------------------
#


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
