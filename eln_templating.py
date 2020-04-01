# Copyright 2019, Rasmus Sorensen <rasmusscholer@gmail.com>
"""

Prior art, alternative Sublime Text templating packages:

* TemplateNinja - Last update 2013, 2K installs.
* TemplateToolkit - not relevant.
* FileTemplates - Last update 2017, 10K installs. "Not actively maintained."
* SublimeTmpl - Last update 2019, 100K installs. Templates for HTML, JS, CSS, PHP, Ruby, Python.
* ProjectMaker
* FileHeader


"""

from __future__ import print_function, absolute_import
import os
from datetime import date, datetime
from collections import OrderedDict, deque
import string
import urllib.parse
import sublime
import sublime_plugin
import logging
from .eln_utils import get_setting, get_settings
logger = logging.getLogger(__name__)


def print_status_msg(msg, prefix="ELN-Utils: "):
    """ Convenience function to both print a message to stdout in the console and show it in the status area. """
    print(prefix + msg)
    sublime.status_message(prefix + msg)


class CollectUserInputCommand(sublime_plugin.WindowCommand):
    """
    A generic command with a method for collecting a list of user-input.
    Usage:

    In `__init__` (*after* calling super), or in `run`,
    set `self.requested_userinput` to a list of (key, description) tuples.
    At the end of your `run` method, invoke `collect_userinput()`.
    Continue your Command logic in a method named `done_collecting_userinput`, overwriting this baseclass' method.
    The requested user inputs will be available as `self.collected_userinput` (ordered dict),
    and `done_collecting_userinput()` is called when all inputs have been collected.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.collected_userinput = OrderedDict()
        self.requested_userinput = deque([])  # list of tuples. Will be converted to a deque.
        self.current_input = None
        self.completed_userinput = []

    def collect_userinput(self):
        # for key, desc in self.requested_userinput:
        # Nope, for-loop isn't really compatible with SublimeText's input model (which takes a function).
        print("Starting user input collection. Requested inputs =", self.requested_userinput)
        if isinstance(self.requested_userinput, list):
            self.requested_userinput = deque(self.requested_userinput)
        self.drive_userinput_chain()  # recursively

    def drive_userinput_chain(self, value=None):
        print("Last user input %r = %r" % (self.current_input, value))
        if value is not None:
            self.collected_userinput[self.current_input] = value
            self.completed_userinput.append(self.current_input)
        try:
            key, desc = self.requested_userinput.popleft()
            self.current_input = key
            # self.window.show_input_panel(caption, initial_text, on_done, on_change, on_cancel)
            print("Prompting for user input %r (%r)" % (desc, key))
            self.window.show_input_panel(desc, '', self.drive_userinput_chain, None, None)
        except IndexError:
            print("\nAll user inputs collected:")
            # print("\n".join(f" - {k}: {v}" for k, v in self.collected_userinput.items()))  # ST is python 3.3
            print("\n".join(" - {}: {}".format(k, v) for k, v in self.collected_userinput.items()))
            self.done_collecting_userinput()

    def done_collecting_userinput(self):
        print(" - Done! But this method should be overwritten by the sub-class.")

    def show_error(self, desc, exc):
        msg = "{}: {}: {}".format(desc, exc.__class__.__name__, exc)
        print(msg)
        self.window.status_message(msg)
        sublime.error_message(msg)


class ElnCreateNewProjectCommand(CollectUserInputCommand):
    """
    Command string: eln_create_new_project
    Create a new project:
    - project folder, if eln_projects_basedir is specified.
    - new project page/file (in new buffer), if eln_projects_title_fmt is boolean true.
    - load buffer with template, if mediawiker_experiments_template
    --- and fill in template argument, as specified by eln_projects_template_args

    This is a window command, since we might not have any views open when it is invoked.

    Question: Does Sublime wait for window commands to finish, or are they dispatched to run
    asynchronously in a separate thread? ST waits for one command to finish before a new is invoked.
    In other words: *Commands cannot be used as functions*. That makes ST plugin development a bit convoluted.
    It is generally best to avoid any "run_command" calls, until the end of any methods/commands.

    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def run(self):
        self.requested_userinput = get_setting('eln_projects_userinput')
        if self.requested_userinput is None:
            self.requested_userinput = [
                ("projectid", "Project Identifier"),
                ("titledesc", "Title description"),
            ]
        self.buffer_text = ""
        self.collect_userinput()  # calls self.done_collecting_userinput() when done.

    def done_collecting_userinput(self, *args, **kwargs):
        """
        Called when all user input have been collected.
        Settings:
            'eln_projects_basedir'
            'eln_projects_title_fmt'
            'eln_projects_filename_fmt'
            'eln_projects_filename_quote'
            'eln_projects_filename_quote_safe'
            'eln_projects_foldername_fmt'
            'eln_projects_template'
            'eln_projects_template_subst_mode'
            'eln_projects_template_kwargs'
            'eln_experiments_save_to_file'
            'eln_experiments_enable_autosave'
            # 'eln_experiments_overview_page'
        """
        print("\nCreating new project:")
        print("\n".join(" - {}: {}".format(k, v) for k, v in self.collected_userinput.items()))
        # Ways to format a date/datetime as string: startdate.strftime("%Y-%m-%d"), or "{:%Y-%m-%d}".format(startdate)

        # Non-attribute settings:
        startdate = date.today().isoformat()    # datetime.now()
        # The base directory where the user stores his experiments, e.g. /home/me/documents/experiments/
        settings = get_settings()
        basedir = settings.get('eln_projects_basedir')
        if basedir is None:
            raise ValueError("'eln_projects_basedir' must be defined in your configuration, aborting.")
        if basedir:
            basedir = os.path.abspath(os.path.expanduser(basedir))
        # title format, e.g. "MyExperiments/{expid} {titledesc}". If not set, no new buffer is created.
        title_fmt = settings.get('eln_projects_title_fmt', '{expid} {titledesc}')
        filename_fmt = settings.get('eln_projects_filename_fmt', '{expid}.md')
        # quoting filename. 'quote' is for url paths, 'quote_plus' is for form data (uses '+' for spaces)
        filename_quote = settings.get('eln_projects_filename_quote', None)  # None, 'quote', or 'quote_plus'
        filename_quote_safe = settings.get('eln_projects_filename_quote_safe', '')  # don't touch these chars
        # How to format the folder, e.g. "{expid} {titledesc}"
        # If exp_foldername_fmt is not specified, use title_fmt - remove any '/' and whatever is before it
        foldername_fmt = settings.get('eln_projects_foldername_fmt', (title_fmt or '').split('/')[-1])
        # Template settings:
        template_fn = settings.get('eln_projects_template')
        if template_fn is None:
            print("Note: 'eln_projects_template' is not specified in config.")
        if template_fn and template_fn.startswith("~"):
            template_fn = os.path.expanduser(template_fn)
        # template parameters substitution mode. Can be any of 'python-fmt', 'python-%' or 'mediawiki'.
        template_subst_mode = settings.get('eln_projects_template_subst_mode', 'python-fmt') or 'python-fmt'
        # Additional user-customized args to feed to the template. (Mostly for shared templates).
        template_kwargs = settings.get('eln_projects_template_kwargs', {}) or {}
        template_kwargs.update(self.collected_userinput)
        # If save_to_file is True, the view/buffer is saved locally immediately upon creation:
        # Experiments overview page: A file/page that lists (and links) to all projects.
        overview_page = settings.get('eln_projects_overview_page')
        if overview_page and overview_page[0] == '~':
            overview_page = os.path.expanduser(overview_page)
            print(" - overview_page:", overview_page)
        save_to_file = settings.get('eln_experiments_save_to_file', True)
        # Enable auto save. Requires auto-save plugin. github.com/scholer/auto-save
        enable_autosave = settings.get('eln_experiments_enable_autosave', False)

        if not any(value for value in self.collected_userinput.values()):
            # If both expid and exp_title are empty, just abort:
            print("All user-inputs were empty, aborting...")
            return

        # 1. Make experiment folder, if appropriate:
        foldername = folderpath = None
        if basedir and foldername_fmt:
            basedir = basedir.strip()
            if os.path.isdir(basedir):
                try:
                    foldername = foldername_fmt.format(**template_kwargs).strip()
                except KeyError as exc:
                    self.show_error("Error creating foldername from format string %r" % foldername_fmt, exc=exc)
                    return
                folderpath = os.path.join(basedir, foldername)
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
                msg = "ERROR: Configured project base dir does not exists: %s" % (basedir,)
            print(msg)
            sublime.status_message(msg)
        else:
            print("WARNING: exp_basedir or foldername_fmt not defined: %s, %s" % (basedir, foldername_fmt))

        # 2. Make new view, if title_fmt is specified:
        try:
            title = title_fmt.format(**template_kwargs)
        except KeyError as exc:
            self.show_error("Error creating title from format string %r" % title_fmt, exc=exc)
            return
        template_kwargs.update(title=title, pagetitle=title)
        self.view = exp_view = sublime.active_window().new_file()  # Make a new file/buffer/view
        self.window.focus_view(exp_view)  # exp_view is now the window's active_view
        view_default_dir = folderpath
        try:
            filename = filename_fmt.format(**template_kwargs)
        except KeyError as exc:
            self.show_error("Error creating filename from format string %r" % filename_fmt, exc=exc)
            return
        if filename_quote:
            if filename_quote == 'quote_plus':
                filename = urllib.parse.quote_plus(filename, safe=filename_quote_safe)
            elif filename_quote == 'quote':
                filename = urllib.parse.quote(filename, safe=filename_quote_safe)
        if view_default_dir:
            view_default_dir = os.path.expanduser(view_default_dir)
            print("Setting view's default dir to:", view_default_dir)
            exp_view.settings().set('default_dir', view_default_dir)  # Update the view's working dir.
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
        if not template_fn:
            print_status_msg('No template specified (settings key "eln_experiments_template").')

        if template_fn:
            # Load the template: #
            print("Using template:", template_fn)
            try:
                # Open user configured local template file:
                with open(template_fn, encoding='utf-8') as fd:
                    template_content = fd.read()
                print(" - Template loaded from disk; length:", len(template_content))
            except FileNotFoundError as exc:
                print("ERROR: Could not open template file:", template_fn, "(%s)" % exc)
                return

            # Perform template variable substitution:
            # Update kwargs with user input and today's date:
            template_kwargs.update({
                'filename': filename, 'foldername': foldername, 'filepath': filepath, 'folderpath': folderpath,
                'startdate': startdate, 'date': startdate
            })
            if template_subst_mode == 'python-fmt':
                # template_kwargs must be dict/mapping: (template_args_order no longer supported)
                try:
                    template_content = template_content.format(**template_kwargs)
                except KeyError as exc:
                    self.show_error("Error interpolating template (%r) with template vars" % template_fn, exc=exc)
                    return
                # except KeyError as exc:
                #     print("%s: Unknown template variable %s" % (exc.__class__.__name__, exc))
                #     sublime.status_message("ERROR: Unrecognized variable name in template: %s" % (exc,))
                #     raise exc
            elif template_subst_mode == 'python-%':
                # "%s" string interpolation: template_vars must be tuple or dict (both will work):
                template_content = template_content % template_kwargs
            else:
                print("Unrecognized template_subst_mode '%s'" % (template_subst_mode,))

            # Add template to buffer text string:
            # self.exp_buffer_text = "".join(text.strip() for text in (self.exp_buffer_text, template_content))
            self.buffer_text += template_content


        # 6. Append self.exp_buffer_text to the view:
        exp_view.run_command('eln_insert_text', {'position': exp_view.size(), 'text': self.buffer_text})

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
        #             # To write strings to files opened in binary mode, cast the string to bytes (encode them):
        #             # >>> fd.write(bytes(mystring, 'UTF-8')) *or* fd.write(mystring.encode('UTF-8'))
        #             fd.write(link_text) # The format should include newline if desired.
        #         print("Appended %s chars to file '%s" % (len(link_text), experiments_overview_page))
        #     else:
        #         # User probably specified a page on the wiki. (This is not yet supported.)
        #         # Even if this is a page on the wiki, you should check whether that page is already opened in Sublime.
        #         # Consider: Implement specifying experiments_overview_page from server.
        #         print("Using experiment_overview_page from the server is not yet supported.")

        print("ElnCreateNewProjectCommand completed!\n")
        if save_to_file:
            self.window.run_command("save")
        if enable_autosave:
            self.window.run_command("auto_save", args={"enable": True})


class ElnCreateNewExperimentCommand(sublime_plugin.WindowCommand):
    """
    Command string: eln_create_new_experiment
    Create a new experiment:
    - exp folder, if mediawiker_experiments_basedir is specified.
    - new wiki page (in new buffer), if mediawiker_experiments_title_fmt is boolean true.
    - load buffer with template, if mediawiker_experiments_template
    --- and fill in template argument, as specified by mediawiker_experiments_template_args
    - Done: Create link to the new experiment page and append it to experiments_overview_page.
    - Done: Move this command to rsenv.eln package.
    - Done: Option to save view buffer to file.
    - Done: Option to enable auto_save
    This is a window command, since we might not have any views open when it is invoked.

    Question: Does Sublime wait for window commands to finish, or are they dispatched to run
    asynchronously in a separate thread? ST waits for one command to finish before a new is invoked.
    In other words: *Commands cannot be used as functions*. That makes ST plugin development a bit convoluted.
    It is generally best to avoid any "run_command" calls, until the end of any methods/commands.

    # TODO: Update this to use the common CollectUserInputCommand.

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
        print("\nCreating new experiment (expid=%s, titledesc=%s, dummy=%s..." % (self.expid, self.titledesc, dummy))
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
            print(" - experiments_overview_page:", experiments_overview_page)
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
                        os.makedirs(folderpath, exist_ok=False)
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
        self.view = exp_view = sublime.active_window().new_file()  # Make a new file/buffer/view
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
            exp_view.settings().set('default_dir', view_default_dir)  # Update the view's working dir.
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
                with open(template, encoding='utf-8') as fd:
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
            elif template_subst_mode in ('python-$', 'template-string'):
                template_string_obj = string.Template(template_content)
                template_content = template_string_obj.safe_substitute(**template_kwargs)
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
        #             # To write strings to files opened in binary mode, cast the string to bytes (encode them):
        #             # >>> fd.write(bytes(mystring, 'UTF-8')) *or* fd.write(mystring.encode('UTF-8'))
        #             fd.write(link_text) # The format should include newline if desired.
        #         print("Appended %s chars to file '%s" % (len(link_text), experiments_overview_page))
        #     else:
        #         # User probably specified a page on the wiki. (This is not yet supported.)
        #         # Even if this is a page on the wiki, you should check whether that page is already opened in Sublime.
        #         # Consider: Implement specifying experiments_overview_page from server.
        #         print("Using experiment_overview_page from the server is not yet supported.")

        print("ElnCreateNewExperimentCommand completed!\n")
        if save_to_file:
            self.window.run_command("save")
        if enable_autosave:
            self.window.run_command("auto_save", args={"enable": True})


