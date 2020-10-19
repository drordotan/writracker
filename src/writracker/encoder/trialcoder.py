"""
coding strokes & characters in one trial
"""
import numpy as np
import re
# noinspection PyPep8Naming
import PySimpleGUI as sg
import tkinter as tk
import pyautogui
from tkinter import messagebox

from writracker.encoder import dataio, manip

app_config = dict(max_within_char_overlap=0.25,
                  error_codes=('WrongNumber', 'NoResponse', 'BadHandwriting', 'TooConnected'),
                  response_mandatory=True,
                  show_extending=True,
                  dot_radius=3)

CYANS = ["#00FFFF", "#A0FFFF", "#C0FFFF"]
PURPLES = ["#BF0FF8", "#CE54F5", "#E191FA"]

ORANGES = ["DarkOrange1", "DarkOrange2", "DarkOrange3"]
REDS = ["#FF0000", "#FF8080", "#FFA0A0"]

RED = "#FF0000"
GREEN = "#00FF00"
YELLOW = "#FFFF00"

# root = tk.Tk()
# screen_width = root.winfo_screenwidth()
# screen_height = root.winfo_screenheight()
width, height = pyautogui.size()

# full_window = app.desktop().frameGeometry()            # get desktop resolution
#         self.resize(full_window.width(), full_window.height())  # set window size to full screen
#         self.move(0, 0)


#-------------------------------------------------------------------------------------
def encode_one_trial(trial, out_dir, screen_size=(1000, 800), margin=25):
    """
    fully encode one trial.
    If the trial is split in two: encode both halves

    Return what to do next: quit, next, prev, or choose_trial
    """

    #-- trial_queue usually contains just one element, unless we split a trial into 2 trials
    trial_queue = _init_trial_queue(trial)
    sub_trial_num = 1

    user_response_as_text = None

    while len(trial_queue) > 0:

        # noinspection PyUnresolvedReferences
        characters = trial_queue.pop(0)

        #-- This small loop runs the trial-encoding screen
        rc = 'continue'
        while rc == 'continue':
            rc, characters, extra_info = \
                _try_encode_trial(trial, characters, sub_trial_num, out_dir, screen_size, margin, user_response_as_text)

        user_response_as_text = None

        #-- Check what to do next: continue to another trial, or open another popup for the same trial

        if rc == 'quit':
            return 'quit'

        elif rc == 'settings':
            show_settings_screen()
            trial_queue = _init_trial_queue(trial)
            sub_trial_num = 1

        elif rc == 'choose_trial':
            return 'choose_trial'

        elif rc == 'reset_trial':
            trial_queue = _init_trial_queue(trial)
            sub_trial_num = 1
            dataio.delete_trial(out_dir, trial.trial_id)
            trial.processed = False

        elif rc == 'split_trial':
            # noinspection PyUnboundLocalVariable
            trial_queue.insert(0, extra_info)
            trial_queue.insert(0, characters)

        elif rc == 'next_trial':
            sub_trial_num += 1
            pass

        elif rc == 'prev_trial':
            return 'prev'

        elif rc == 'split_stroke':
            stroke = extra_info
            dot = _split_stroke(stroke, screen_size, margin)
            if dot is not None:
                characters = manip.split_stroke(characters, stroke, dot)
            trial_queue.insert(0, characters)

        elif rc == 'rerun':
            trial_queue.insert(0, characters)
            user_response_as_text = extra_info

        else:
            raise Exception('Bug: unknown rc ({})'.format(rc))

    return 'next'


def _init_trial_queue(trial):
    return [manip.create_default_characters(trial.traj_points, app_config['max_within_char_overlap'])]


#-------------------------------------------------------------------------------------
def show_settings_screen(show_cancel_button=True):
    """
    Open the 'settings' window
    """

    show_popup = True
    warning = ''

    while show_popup:

        buttons = [sg.Button('OK')]
        if show_cancel_button:
            buttons.append(sg.Button('Cancel'))

        layout = [
            [sg.Text(warning, text_color='red')],

            [sg.Checkbox('Typing in the participants\'s response is mandatory', default=app_config['response_mandatory'], key='response_mandatory')],

            [sg.Text('Merge 2 strokes into one character if their horizontal overlap exceeds'),
             sg.InputText('{:.1f}'.format(100*app_config['max_within_char_overlap']), key='max_within_char_overlap'),
             sg.Text('percent')],

            [sg.Text('Error codes (comma-separated list): '), sg.InputText(','.join(app_config['error_codes']), key='error_codes')],

            [sg.Text('The size of dots for plotting the trajectories: '),
             sg.DropDown(['1', '2', '3', '4', '5'], readonly=True, key='dot_radius', default_value=str(app_config['dot_radius']))],
            buttons,
        ]

        window = sg.Window('Settings', layout)

        event = None
        clicked_ok = False
        values = {}

        while event is None:
            event, values = window.Read()
            clicked_ok = event == 'OK'

        window.Close()

        if clicked_ok:
            response_mandatory = values['response_mandatory']
            max_within_char_overlap_s = values['max_within_char_overlap']
            error_codes = values['error_codes']
            dot_radius = values['dot_radius']

            try:
                max_within_char_overlap = float(max_within_char_overlap_s)
            except ValueError:
                warning = 'Invalid "Maximal overlap" value'
                continue

            if not (0 < max_within_char_overlap < 100):
                warning = 'Invalid "Maximal overlap" value (expecting a value between 0 and 100)'
                continue

            if not re.match('([a-zA-Z_]+)(,[a-zA-Z_]+)*', error_codes):
                warning = 'Error codes must be a comma-separated list of letter codes, without spaces'
                continue

            app_config['response_mandatory'] = response_mandatory
            app_config['max_within_char_overlap'] = max_within_char_overlap / 100
            app_config['error_codes'] = error_codes.split(',')
            app_config['dot_radius'] = int(dot_radius)

            show_popup = False

        else:
            show_popup = False


#-------------------------------------------------------------------------------------
def _try_encode_trial(trial, characters, sub_trial_num, out_dir, screen_size, margin, response):
    """"
    returns in this order: rc, characters, extra_info
    """
    strokes = [s for c in characters for s in c.on_paper_strokes]
    all_markup_dots = [dot for c in characters for dot in c.on_paper_dots]

    #-- Skipping empty trials
    if len(strokes) == 0:
        dataio.save_trial(trial, '', 'empty', characters, sub_trial_num, out_dir)
        trial.processed = True
        return 'next_trial', None, None

    on_paper_chars = [c for c in characters if len(c.trajectory) > 0]
    on_paper_strokes = [s for s in strokes if len(s.trajectory) > 0]

    expand_ratio, offset, screen_size = _get_expand_ratio(all_markup_dots, screen_size, margin)

    title = 'Trial #{}, target={} ({} characters, {} strokes) '\
        .format(trial.trial_id, trial.stimulus, len(on_paper_chars), len(on_paper_strokes))

    window = _create_window_for_markup(screen_size, title, response or '')

    if len(on_paper_chars) < 2:
        window['merge_chars'].update(disabled=True)
        window['split_trial'].update(disabled=True)

    window['accept_error'].update(disabled=True)

    graph = window.Element('graph')
    instructions = window.Element('instructions')

    _plot_dots_for_markup(characters, graph, screen_size, expand_ratio, offset, margin)

    selection_handler = None
    current_command = None

    while True:

        cleanup_selection_handler = False

        event, values = window.Read()

        m = re.match('.+:(\\d+)', event)
        if m is not None:
            event = int(m.group(1))

        #-- Window was closed: reset the trial
        if event is None:
            return 'reset_trial', None, None

        #-- Reset the trial
        elif event in ('r', 'R', 'reset_trial', 82, 'ר'):
            answer = sg.Popup('Reset trial', 'Are you sure you want to reset the current trial?', button_type=1)
            if answer == "Yes":
                window.Close()
                return 'reset_trial', None, None

        #-- Quit the app
        elif event in ('q', 'Q', 'quit', '/'):
            answer = sg.Popup('Quit', 'Are you sure you want to quit WEncoder?', button_type=1)
            if answer == "Yes":
                window.Close()
                return 'quit', None, None

        #-- Select trial
        elif event in ('g', 'G', 'choose_trial', 71, 'ע'):
            window.Close()
            return 'choose_trial', None, None

        #-- Open settings window
        elif event in ('e', 'E', 'settings', 69, 'ק'):
            window.Close()
            return 'settings', None, None

        #-- OK - Accept current coding
        if event in ('a', 'A', 'accept', 65, 'ש'):
            response = get_valid_user_response(response, on_paper_chars, get_if_already_exists=False)
            if response is not None:
                if sub_trial_num == 1:
                    dataio.delete_trial(out_dir, trial.trial_id)
                dataio.save_trial(trial, response, "OK", characters, sub_trial_num, out_dir)
                trial.processed = True
                window.Close()
                return 'next_trial', None, None

        #-- Clicked on DropDown error
        elif event == 'error_code':
            if values['error_code'] in app_config["error_codes"]:
                window['accept_error'].update(disabled=False)
                #window['accept'].update(disabled=True)

            # else:
            #     window['accept_error'].update(disabled=True)

        #-- Error - Accept current coding, set trial as error
        elif event in ('o', 'O', 'accept_error', 79, 'ם'):
            if trial.response is not None or not app_config['response_mandatory']:
                if sub_trial_num == 1:
                    dataio.delete_trial(out_dir, trial.trial_id)
                dataio.save_trial(trial, response, values['error_code'], characters, sub_trial_num, out_dir)
                trial.processed = True
                window.Close()
                return 'next_trial', None, None

        #-- Skip this trial
        elif event in ('k', 'K', 'skip_trial', 75, 'ל'):
            window.Close()
            return 'next_trial', None, None

        #-- Return to previous trial
        elif event in ('p', 'P', 'prev_trial', 80, 'פ'):
            window.Close()
            return 'prev_trial', None, None

        #-- Merge 2 characters
        elif event in ('m', 'M', 'merge_chars', 77, 'צ'):
            if current_command is None and len(characters) > 1:
                instructions.Update('Select the characters to merge. ENTER=confirm, ESC=abort')
                current_command = 'merge_chars'
                selection_handler = _CharsSelectorConsecutivePair(graph, characters)

        #-- Split a stroke into 2 characters
        elif event in ('s', 'S', 'split_stroke', 83, 'ד'):
            if current_command is None:
                instructions.Update('Select a stroke to split. ENTER=confirm, ESC=abort')
                current_command = 'split_stroke'
                selection_handler = _SingleStrokeSelector(graph, strokes)

        #-- Split a character
        elif event in ('c', 'C', 'split_char', 67, 'ב'):
            if current_command is None:
                instructions.Update('Select a character to split to 2 different characters. ENTER=confirm, ESC=abort')
                current_command = 'split_char'
                selection_handler = _MultiStrokeSelector(graph, characters, 'before')

        #-- Split the trial into 2 trials
        elif event in ('t', 'T', 'split_trial', 84, 'א'):
            if current_command is None:
                instructions.Update('Select the last character of trial#1. ENTER=confirm, ESC=abort')
                current_command = 'split_trial'
                selection_handler = _CharSeriesSelector(graph, characters)


        #-- Self correction
        elif event in ('x', 'X', 'set_extending_chars', 'ס'):
            if current_command is None:
                instructions.Update('Select 2 characters to connect as extending, or 1 char to un-extend. ENTER=confirm, ESC=abort')
                current_command = 'set_extending_chars'
                selection_handler = _CharSelectorAnyPair(graph, characters)

        # -- Show Self correction
        elif event == 'show_extending':
            app_config['show_extending'] = values['show_extending']
            window.Close()
            return 'rerun', characters, None

        elif event in ('d', 'D', 'delete_stroke', 68, 'ג'):
            if current_command is None:
                instructions.Update('Select a stroke to delete. ENTER=confirm, ESC=abort')
                current_command = 'delete_stroke'
                selection_handler = _SingleStrokeSelector(graph, strokes)

        elif event == 'enter_response':
            response = get_valid_user_response(response, on_paper_chars, get_if_already_exists=True)
            window.Close()
            return 'rerun', characters, response

        #-- Mouse click
        elif event == 'graph':
            if selection_handler is not None:
                selection_handler.clicked(values)

        #-- ENTER clicked: end the currently-running command

        elif current_command is not None and not isinstance(event, int) and len(event) == 1 and ord(event) == 13:
            if current_command == 'split_char':
                characters = manip.split_character(characters, selection_handler.selected_char, selection_handler.selected_stroke)
                window.Close()
                return 'continue', characters, None

            elif current_command == 'merge_chars':
                characters = manip.merge_characters(characters, selection_handler.selected)
                window.Close()
                return 'continue', characters, None

            elif current_command == 'split_stroke':
                if selection_handler.selected is None:
                    return 'continue', characters, None
                window.Close()
                return 'split_stroke', characters, selection_handler.selected

            elif current_command == 'split_trial':
                if selection_handler.selected is None:
                    return 'continue', characters, None
                chars1, chars2 = manip.split_into_2_trials(characters, selection_handler.selected)
                window.Close()
                return 'split_trial', chars1, chars2

            elif current_command == 'set_extending_chars':
                if len(selection_handler.selected_chars) == 0:
                    return 'continue', characters, None
                _set_extending_characters(characters, selection_handler)
                window.Close()
                return 'rerun', characters, None

            elif current_command == 'delete_stroke':
                window.Close()
                try:
                    characters, err_msg = manip.delete_stroke(characters, selection_handler)
                    if err_msg is not None:
                        messagebox.showerror('Invalid deletion attempt', err_msg)
                    return 'rerun', characters, None
                except Exception as e:
                    messagebox.showerror('Error in WEncoder', 'Error when trying to delete a character: {}'.format(e))
                    return 'rerun', characters, None

            else:
                messagebox.showerror('Error in WEncoder', 'General error (ENC-GEN-01)\nQuitting')
                return 'quit', None, None

        #-- ESC clicked: cancel the currently-running command
        #elif len(event) == 1 and ord(event) == 27:                         #Original line!!!

        else:
            if isinstance(event, str) and len(event) == 1:
                print("Clicked [{}] (#{})".format(event, ord(event)))
            else:
                print("Clicked [{}]".format(event))
            instructions.Update('UNKNOWN COMMAND')

        if current_command is not None and (event == 27 or (isinstance(event, str) and len(event) == 1 and ord(event) == 27)):
            cleanup_selection_handler = True

        if cleanup_selection_handler:
            instructions.Update('')
            current_command = None
            #if selection_handler is not None:
            selection_handler.cleanup()
            selection_handler = None


#-------------------------------------------------------------------------------------
def response_ok(response, on_paper_chars):
    n_chars = len(on_paper_chars)
    if response is None or response == '':
        return not app_config['response_mandatory']
    else:
        return len(response) == n_chars


#-------------------------------------------------------------------------------------
def get_valid_user_response(response, on_paper_chars, get_if_already_exists=True):
    """
    Get a response from the user, update the trial.

    :param response:
    :param on_paper_chars:
    :param get_if_already_exists: Whether to get a response if the trial already contains a valid response
    :return: True if a valid response was entered. False if CANCEL was clicked.
    """

    orig_response = response
    if response is None:
        response = ''

    force_get = get_if_already_exists
    while force_get or not response_ok(response, on_paper_chars):
        response = sg.popup_get_text('Please enter a response with exactly {} letters/digits.'.format(len(on_paper_chars)),
                                     title='Enter response')
        if response is None:  # CANCEL clicked
            return orig_response
        elif response == '':
            return ''

        force_get = False

    return response


#-------------------------------------------------------------------------------------
def _create_window_for_markup(screen_size, title, user_response):

    commands_c = [
        sg.Text('Trial-level: '),
        sg.Button('(R)eset current trial', key='reset_trial'),
        sg.Button('Split (T)rial', key='split_trial'),
        sg.Text('            Stroke-level: '),
        sg.Button('Split (S)troke', key='split_stroke'),
        sg.Button('(D)elete stroke', key='delete_stroke'),
    ]

    commands_s = [
        sg.Text('Character-level: '),
        sg.Button('Split (C)har', key='split_char'),
        sg.Button('(M)erge chars', key='merge_chars'),
        sg.Button('E(x)tend char', key='set_extending_chars'),
        sg.Checkbox('Show extending chars', key='show_extending', enable_events=True, default=app_config['show_extending']),
    ]

    commands_nav = [
        sg.Text('Navigation / decision: '),
        sg.Button('(A)ccept as OK', key='accept'),
        sg.Button('Err(o)r:', key='accept_error'),
        sg.DropDown(app_config['error_codes'], key='error_code', enable_events=True, readonly=True, background_color='#FFFFFF'),
        sg.Button('s(K)ip current trial', key='skip_trial'),
        sg.Button('(P)revious trial', key='prev_trial'),
        sg.Button('(G)o to specific trial', key='choose_trial'),
    ]

    commands_resp = [
        sg.Txt('User response:'),
        sg.Input(default_text=user_response, key='user_response', readonly=True, background_color='#CFCFCF'),
        sg.Button('Update...', key='enter_response'),
    ]

    commands_general = [
        sg.Button('S(E)ttings', key='settings'),
        sg.Button('(Q)uit WEncoder', key='quit'),
    ]

    layout = [
        [sg.Text(' ' * 200, text_color='white', key='instructions', font=('Arial', 16))],
        [sg.Graph(screen_size, (0, screen_size[1]), (screen_size[0], 0), background_color='Black', key='graph', enable_events=True)],
        commands_c,
        commands_s,
        commands_nav,
        commands_resp,
        commands_general
    ]

    label = tk.Label(text="Hello, Tkinter", fg="white", bg="yellow")
    label.pack()

    window = sg.Window(title, layout, return_keyboard_events=True,  resizable=True)
    window.Finalize()
    return window


#-------------------------------------------------------------------------------------
def _plot_dots_for_markup(characters, graph, screen_size, expand_ratio, offset, margin):

    dot_radius = app_config['dot_radius']

    dot_num = 0
    char_index = 0
    for char in characters:
        char_index += 1
        strokes = char.on_paper_strokes

        if char.extends is None:
            color = ORANGES if char.char_num % 2 == 1 else CYANS
        elif not app_config['show_extending']:
            continue
        else:
            color = REDS if char.char_num % 2 == 1 else PURPLES

        for i in range(len(strokes)):
            stroke = strokes[i]

            stroke.color = color[i] if i < len(color) else color[-1]

            for dot in stroke.trajectory:
                x = (dot.x - offset[0]) * expand_ratio + margin
                y = (dot.y - offset[1]) * expand_ratio + margin
                y = screen_size[1] - y
                #x = screen_size[1] - x
                dot.screen_x = x
                dot.screen_y = y
                dot.ui = graph.TKCanvas.create_oval(x - dot_radius, y - dot_radius, x + dot_radius, y + dot_radius, fill=stroke.color)
                dot_num = dot_num + 1

            stroke_name = "{}.{}".format(char_index, i+1)
            if char.extends is not None:
                stroke_name += "(E{})".format(char.extends)
            # noinspection PyUnboundLocalVariable
            graph.TKCanvas.create_text(x+2, y+2, fill='yellow', text=stroke_name, anchor=tk.NW)


#-------------------------------------------------------------------------------------
def _split_stroke(stroke, screen_size, margin, dot_radius=6):
    """
    Open the "split stroke" popup, and run the splitting
    """

    expand_ratio, offset, screen_size = _get_expand_ratio(stroke, screen_size, margin)
    window = _create_window_for_split_strokes(screen_size)

    graph = window.Element('graph')

    dots = _plot_dots_for_split(stroke.trajectory, graph, screen_size, expand_ratio, offset, margin, dot_radius)

    selected_dot = None

    while True:

        event, values = window.Read()
        if event is None:
            #-- Window closed
            return None

        if event == 'graph':
            click_coord = values['graph']
            if click_coord[0] is None:
                continue

            clicked_dot = _find_clicked_dot(dots, click_coord)
            for dot in dots:
                graph.TKCanvas.itemconfig(dot.ui, fill=dot.color)

            for dot in dots:
                if dot.t <= clicked_dot.t:
                    graph.TKCanvas.itemconfig(dot.ui, fill='#00FF00')

            selected_dot = clicked_dot

        elif len(event) == 1 and ord(event) == 13 and selected_dot is not None:
            #-- ENTER pressed
            window.Close()
            return selected_dot.markup

        elif event == 'Escape:27':
            #-- ESC pressed
            if selected_dot is None:
                window.Close()
                return None
            else:
                for dot in dots:
                    graph.TKCanvas.itemconfig(dot.ui, fill=dot.color)
                selected_dot = None


#-------------------------------------------------------------------------------------
def _create_window_for_split_strokes(screen_size):

    layout = [
        [sg.Text('Choose a dot on which the stroke will be split. ENTER=confirm, ESC=abort', text_color='red', key='instructions')],
        [sg.Graph(screen_size, (0, screen_size[1]), (screen_size[0], 0), background_color='Black', key='graph', enable_events=True)]
    ]

    window = sg.Window('Split a stroke into 2', layout, return_keyboard_events=True, resizable=True)
    window.Finalize()

    return window


#-------------------------------------------------------------------------------------
def _plot_dots_for_split(dot_list, graph, screen_size, expand_ratio, offset, margin, dot_radius=6, n_colors=10):

    darkest_color = 100
    color_range = 255 - darkest_color

    dots = np.array(dot_list)
    ui_dots = []

    z = np.array([dot.z for dot in dots])
    z = np.round(z / max(z) * n_colors)

    for z_level in range(n_colors+1):
        curr_level_dots = dots[z == z_level]
        if len(curr_level_dots) == 0:
            continue

        color = round(darkest_color + color_range * (z_level/n_colors))
        color = "#" + ("%02x" % color) * 3

        for dot in curr_level_dots:
            uidot = UiTrajPointForSplit(dot, color)

            x = (dot.x - offset[0]) * expand_ratio + margin
            y = (dot.y - offset[1]) * expand_ratio + margin
            y = screen_size[1] - y
            uidot.screen_x = x
            uidot.screen_y = y
            uidot.ui = graph.TKCanvas.create_oval(x - dot_radius, y - dot_radius, x + dot_radius, y + dot_radius, fill=color)
            ui_dots.append(uidot)

    assert sum([d is None for d in ui_dots]) == 0

    return ui_dots


#-------------------------------------------------------------------------------------
class UiTrajPointForSplit(object):

    def __init__(self, markup, color):
        self.markup = markup
        self.color = color
        self.ui = None

    @property
    def x(self):
        return self.markup.x

    @property
    def y(self):
        return self.markup.y

    @property
    def t(self):
        return self.markup.t


#-------------------------------------------------------------------------------------
class _SingleStrokeSelector(object):
    """
    Handles clicks to select one stroke
    """

    def __init__(self, graph, strokes):
        self.graph = graph
        self.strokes = [s for s in strokes if len(s.trajectory) > 0]
        self.selected = None


    def clicked(self, values):

        click_coord = values['graph']
        if click_coord[0] is None:
            return

        clicked_stroke = _find_clicked_stroke(self.strokes, click_coord)  # finds the selected stroke
        self._set_clicked_stroke_color(clicked_stroke)

    def _set_clicked_stroke_color(self, clicked_stroke):
        if clicked_stroke == self.selected:  # second click on the same stroke
            self.cleanup()
            self.selected = None
        else:
            self.cleanup()  # clean previous stroke color
            self.selected = clicked_stroke
            self.highlight_selected(GREEN)  # colors the selected stroke

    def highlight_selected(self, color):
        _set_stroke_color(self.selected, color, self.graph)


    def cleanup(self):
        if self.selected is not None:
            _set_stroke_color(self.selected, None, self.graph)


#-------------------------------------------------------------------------------------
class _MultiStrokeSelector(object):
    """
    Handles clicks to select several strokes: the user selects one of them, and the selection applies to all strokes before/after
    the selected one.
    """

    def __init__(self, graph, characters, select):
        assert select in ('before', 'after')
        self.graph = graph
        self.characters = [c for c in characters if len(c.on_paper_dots) > 0]
        self.strokes = [s for c in characters for s in c.on_paper_strokes]
        self.selected_stroke = None
        self.selected_char = None
        self._get_strokes_to_highlight = self._get_strokes_before if select == 'before' else self._get_strokes_after


    def clicked(self, values):

        click_coord = values['graph']
        if click_coord[0] is None:
            return

        self.cleanup()

        self.selected_char = _find_clicked_char(self.characters, click_coord)
        if len(self.selected_char.on_paper_strokes) == 1:
            #-- Can't choose a 1-stroke character
            self.selected_char = None
            self.selected_stroke = None
            return

        clicked_stroke = _find_clicked_stroke(self.selected_char.on_paper_strokes, click_coord)
        self._set_clicked_stroke_color(clicked_stroke)


    def _set_clicked_stroke_color(self, clicked_stroke):
        self.selected_stroke = clicked_stroke
        self.highlight_selected(GREEN)


    def highlight_selected(self, color):
        if self.selected_stroke != self.selected_char.strokes[-1]:
            strokes_to_highlight = self._get_strokes_to_highlight()
        else:
            strokes_to_highlight = [self.selected_stroke]

        for s in strokes_to_highlight:
            _set_stroke_color(s, color, self.graph)


    def _get_strokes_before(self):
        return [s for s in self.selected_char.on_paper_strokes if s.stroke_num <= self.selected_stroke.stroke_num]


    def _get_strokes_after(self):
        return [s for s in self.selected_char.on_paper_strokes if s.stroke_num >= self.selected_stroke.stroke_num]


    def cleanup(self):
        if self.selected_stroke is None:
            return

        for c in self.strokes:
            _set_stroke_color(c, None, self.graph)


#-------------------------------------------------------------------------------------
class _SelfCorrectionSelector(_MultiStrokeSelector):

    def __init__(self, graph, characters):
        super().__init__(graph, characters, 'after')


    def _set_clicked_stroke_color(self, clicked_stroke):

        if clicked_stroke == self.selected_stroke:  # second click on the same stroke
            self.cleanup()
            self.selected_stroke = None
            self.selected_char = None

        else:
            self.cleanup()  # clean previous stroke color
            self.selected_stroke = clicked_stroke

            if clicked_stroke.correction:   # colors the selected stroke
                #-- A correction stroke was selected. Unselect all correction strokes from this character
                correction_strokes = [s for s in self.selected_char.strokes if s.correction]
                self.selected_stroke = correction_strokes[0]
                self.highlight_selected(GREEN)  # Resetting a correction stroke
            else:
                self.highlight_selected(YELLOW)  # Marking a correction stroke


#-------------------------------------------------------------------------------------
class _CharSelector(object):
    """
    Handles click to select one character
    """

    def __init__(self, graph, characters):
        self.graph = graph
        self.characters = [c for c in characters if len(c.on_paper_dots) > 0]
        self.selected = None

    #---------------------------------------
    def clicked(self, values):
        click_coord = values['graph']
        if click_coord[0] is None:
            return

        clicked_char = _find_clicked_char(self.characters, click_coord)

        self.cleanup()
        self.selected = clicked_char
        self.highlight_selected()

    #---------------------------------------
    def highlight_selected(self):
        raise Exception('Implement this method')

    #---------------------------------------
    def cleanup(self):
        if self.selected is None:
            return
        _set_chars_color(self.graph, self.characters, None)


#-------------------------------------------------------
def _set_chars_color(graph, chars_to_highlight, color):
    for c in chars_to_highlight:
        _set_char_color(c, color, graph)


#-------------------------------------------------------------------------------------
class _CharsSelectorConsecutivePair(_CharSelector):
    """
    Select two consecutive characters by clicking the first
    """

    def __init__(self, graph, characters):
        super().__init__(graph, characters)

    def highlight_selected(self):
        if self.selected == self.characters[-1]:
            self.selected = self.characters[-2]

        selected_num = self.selected.char_num
        chars_to_highlight = [c for c in self.characters if selected_num <= c.char_num <= selected_num+1]
        _set_chars_color(self.graph, chars_to_highlight, GREEN)


#-------------------------------------------------------------------------------------
class _CharSeriesSelector(_CharSelector):
    """
    Selct a character; highlights all characters until the selected one
    """

    def __init__(self, graph, characters):
        super().__init__(graph, characters)

    def highlight_selected(self):
        selected_num = self.selected.char_num
        chars_to_highlight = [c for c in self.characters if c.char_num <= selected_num]
        _set_chars_color(self.graph, chars_to_highlight, GREEN)


#-------------------------------------------------------------------------------------
class _CharSelectorAnyPair(object):
    """
    Select any two characters
    """

    def __init__(self, graph, characters):
        self.graph = graph
        self.characters = [c for c in characters if len(c.on_paper_dots) > 0]
        self.selected_chars = []

    #---------------------------------------
    def clicked(self, values):
        click_coord = values['graph']
        if click_coord[0] is None:
            return

        clicked_char = _find_clicked_char(self.characters, click_coord)

        self.cleanup()

        if clicked_char in self.selected_chars:
            self.unselect_char(clicked_char)
        elif self.n_selected < 2:
            self.select_char(clicked_char)

        self.highlight_selected()

    #---------------------------------------
    @property
    def n_selected(self):
        """
        Number of selected characters. Extending characters don't count.
        """
        selected_char_nums = {c.char_num if c.extends is None else c.extends for c in self.selected_chars}
        return len(selected_char_nums)

    #---------------------------------------
    def select_char(self, clicked_char):
        if clicked_char in self.selected_chars:
            return

        if clicked_char.extends is None:
            self.selected_chars.append(clicked_char)
        else:
            self.selected_chars.extend([c for c in self.characters if c.char_num == clicked_char.extends or c.extends == clicked_char.extends])

    #---------------------------------------
    def unselect_char(self, clicked_char):
        if clicked_char not in self.selected_chars:
            return

        if clicked_char.extends is None:
            self.selected_chars.remove(clicked_char)
        else:
            for c in self.characters:
                if c.char_num == clicked_char.extends or c.extends == clicked_char.extends:
                    self.selected_chars.remove(c)

    #---------------------------------------
    def highlight_selected(self):
        chars_to_highlight = [c for c in self.characters if c in self.selected_chars]
        _set_chars_color(self.graph, chars_to_highlight, GREEN)

    #---------------------------------------
    def cleanup(self):
        _set_chars_color(self.graph, self.characters, None)

    #---------------------------------------
    def _update_selection(self, clicked_char):
        if clicked_char in self.selected_chars:
            self.unselect_cleanup(clicked_char)
            self.selected_chars.remove(clicked_char)
        else:
            self.selected_chars.append(clicked_char)
            self.highlight_selected()

    def unselect_cleanup(self, clicked_char):
        if clicked_char is not None:
            _set_char_color(clicked_char, None, self.graph)

#-------------------------------------------------------------------------------------
def _get_expand_ratio(dots, screen_size, margin):

    x = [dot.x for dot in dots]
    y = [dot.y for dot in dots]

    min_x = min(x)
    max_x = max(x)
    min_y = min(y)
    max_y = max(y)
    canvas_width = max_x - min_x + 1
    canvas_height = max_y - min_y + 1

    expand_ratio = min((screen_size[0] - margin*2) / canvas_width, (screen_size[1] - margin*2) / canvas_height)
    new_screen_size = round(canvas_width * expand_ratio) + margin * 2, round(canvas_height * expand_ratio) + margin * 2
    return expand_ratio, (min_x, min_y), new_screen_size


#-------------------------------------------------------------------------------------
def _find_clicked_dot(dots, coord):
    distances = [distance2(d, coord) for d in dots]
    closest = np.argmin(distances)
    # noinspection PyTypeChecker
    return dots[closest]


#-------------------------------------------------------------------------------------
def _find_clicked_char(characters, coord):
    characters = [c for c in characters]
    distances = [_get_distance_to_char(s, coord) for s in characters]
    closest = np.argmin(distances)
    # noinspection PyTypeChecker
    return characters[closest]


def _get_distance_to_char(char, coord):
    return min([distance2(dot, coord) for dot in char.on_paper_dots])


#-------------------------------------------------------------------------------------
def _find_clicked_stroke(strokes, coord):
    strokes = [s for s in strokes]
    distances = [_get_distance_to_stroke(s, coord) for s in strokes]
    closest = np.argmin(distances)
    # noinspection PyTypeChecker
    return strokes[closest]


def _get_distance_to_stroke(stroke, coord):
    return min([distance2(dot, coord) for dot in stroke.trajectory])


#-------------------------------------------------------------------------------------
def distance2(dot, coord):
    return (dot.screen_x - coord[0]) ** 2 + (dot.screen_y - coord[1]) ** 2


#-------------------------------------------------------------------------------------
def _set_char_color(char, color, graph):
    for stroke in char.on_paper_strokes:
        _set_stroke_color(stroke, color, graph)


def _set_stroke_color(stroke, color, graph):
    if color is None:
        color = stroke.color
    for dot in stroke:
        graph.TKCanvas.itemconfig(dot.ui, fill=color)


#-------------------------------------------------------------------------------------
def _set_extending_characters(all_chars, selection_handler):

    if selection_handler.n_selected == 1:
        manip.disconnect_extending_characters(selection_handler.selected_chars)
    else:
        manip.set_extending_characters(all_chars, selection_handler.selected_chars)
