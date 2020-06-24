"""
coding strokes & characters in one trial
"""
import PySimpleGUI as sg
import numpy as np
import re
import data
from tkinter import*
import tkinter as tk
from encoder import *
from encoder import dataio



markup_config = dict(max_within_char_overlap=0.25, error_codes=('WrongNumber', 'NoResponse', 'BadHandwriting', 'TooConnected'))



#-------------------------------------------------------------------------------------
def encode_one_trial(trial, out_dir, dot_radius=2, screen_size=(1000, 800), margin=25):
    """
    fully encode one trial.

    Return what to do next: quit, next, prev, or choose_trial
    """

    #-- trial_queue usually contains just one element, unless we split a trial into 2 trials
    trial_queue = [_create_default_characters(trial.traj_points, markup_config['max_within_char_overlap'])]
    sub_trial_num = 0

    selection_handler = None
    show_command = False

    while len(trial_queue) > 0:

        # noinspection PyUnresolvedReferences
        characters = trial_queue.pop(0)
        sub_trial_num += 1

        #-- This small loop runs the trial-encoding screen
        rc = 'continue'
        while rc == 'continue':
            rc, characters, extra_info = _try_encode_trial(trial, characters, sub_trial_num, out_dir, dot_radius, screen_size, margin, selection_handler, show_command)

        #-- Check what to do next: continue to another trial, or open another popup for the same trial

        if rc == 'quit':
            return 'quit'

        elif rc == 'settings':
            _open_settings(markup_config)
            trial_queue = [_create_default_characters(trial.traj_points, markup_config['max_within_char_overlap'])]
            sub_trial_num = 0

        elif rc == 'choose_trial':
            return 'choose_trial'

        elif rc == 'reset_trial':
            trial_queue = [_create_default_characters(trial.traj_points, markup_config['max_within_char_overlap'])]
            dataio.remove_from_trial_index(out_dir, trial.trial_id)
            sub_trial_num = 0
            trial.self_correction = "0"

        elif rc == 'split_trial':
            # noinspection PyUnboundLocalVariable
            trial_queue.insert(0, extra_info)
            trial_queue.insert(0, characters)
            sub_trial_num -= 1

        elif rc == 'next_trial':
            pass

        elif rc == 'prev_trial':
            return 'prev'

        elif rc == 'split_stroke':
            stroke = extra_info
            dot = _split_stroke(stroke, screen_size, margin)
            if dot is not None:
                characters = _apply_split_stroke(characters, stroke, dot)
            trial_queue.insert(0, characters)
            sub_trial_num -= 1

        elif rc == 'self_correction':
            show_command = True
            trial_queue.insert(0, characters)
            sub_trial_num -= 1
            selection_handler = extra_info

        elif rc == 'show_correction':
            show_command = True
            trial_queue.insert(0, characters)
            selection_handler = extra_info

        elif rc == 'delete_stroke':
            trial_queue.insert(0, characters)
            selection_handler = None

        elif rc == 'response':
            trial_queue.insert(0, characters)
            selection_handler = None

        elif rc == 'error_codes':
            trial_queue.insert(0, characters)


        else:
            raise Exception('Bug: unknown rc ({:})'.format(rc))

    return 'next'


#-------------------------------------------------------------------------------------
def _open_settings(config):
    """
    Open the 'settings' window
    """

    show_popup = True
    warning = ''

    while show_popup:

        max_within_char_overlap = sg.InputText('{:.1f}'.format(100 * config['max_within_char_overlap']))
        error_codes = sg.InputText(','.join(config['error_codes']))

        layout = [
            [sg.Text(warning, text_color='red')],
            [sg.Text('Maximal overlap between 2 strokes in the same character (%): '), max_within_char_overlap],
            [sg.Text('Error codes: '), error_codes],
            [sg.Button('OK'), sg.Button('Cancel')],
        ]

        window = sg.Window('Settings', layout)

        event = None
        clicked_ok = False
        values = ()

        while event is None:
            event, values = window.Read()
            clicked_ok = event == 'OK'

        window.Close()

        if clicked_ok:
            max_within_char_overlap_s = values[0]
            error_codes = values[1]
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

            config['max_within_char_overlap'] = max_within_char_overlap / 100
            config['error_codes'] = error_codes.split(',')

            show_popup = False

        else:
            show_popup = False


#-------------------------------------------------------------------------------------
def _try_encode_trial(trial, characters, sub_trial_num, out_dir, dot_radius, screen_size, margin, last_selection_handler, show_checkbox):
    """"
    returns in this order: rc, characters, extra_info
    """
    strokes = [s for c in characters for s in c.on_paper_strokes]
    all_markup_dots = [dot for c in characters for dot in c.on_paper_dots]

    #-- Skipping empty trials
    if len(strokes) == 0:
        trial.rc = 'empty'
        save_trial(trial, characters, sub_trial_num, out_dir)
        return 'next_trial', None, None

    on_paper_chars = [c for c in characters if len(c.trajectory) > 0]
    on_paper_strokes = [s for s in strokes if len(s.trajectory) > 0]

    expand_ratio, offset, screen_size = _get_expand_ratio(all_markup_dots, screen_size, margin)

    title = 'Trial #{:}, target={:} ({:} characters, {:} strokes) ronronron'\
        .format(trial.trial_id, trial.stimulus, len(on_paper_chars), len(on_paper_strokes))
    window = _create_window_for_markup(screen_size, title)

    if len(on_paper_chars) < 2:
        window['merge_chars'].update(disabled=True)
        window['split_trial'].update(disabled=True)
    window['accept_error'].update(disabled=True)




    graph = window.Element('graph')
    instructions = window.Element('instructions')

    _plot_dots_for_markup(characters, graph, screen_size, expand_ratio, offset, margin, dot_radius)


    selection_handler = None
    current_command = None
    window['show_correction'].enable_events = True


    '''if (show_command == True):
        window.FindElement('show_correction').update(disabled=False)'''
    '''else:
        window['show_correction'].update(disabled=True)'''

    # -- Enables self correction button only for 2 or more strokes in a trial
    if len(on_paper_strokes) < 2:
        window['self_correction'].update(disabled=True)
    else:
        window['self_correction'].update(disabled=False)


    while True:


        event, values = window.Read()


        print(event)




        #-- Enables Error button only if an error is selected
        if (values[0] not in markup_config["error_codes"]):
            window['accept_error'].update(disabled=True)
        else:
            window['accept_error'].update(disabled=False)

        #-- Enables self correction checkbox
        if trial.self_correction == "1":
            window['show_correction'].update(disabled = False)



        #-- Window was closed: reset the trial
        if event is None:
            return 'reset_trial', None, None

        #-- Reset the trial
        elif event in ('r', 'R', 'reset_trial'):
            window.Close()
            return 'reset_trial', None, None

        #-- Quit the app
        elif event in ('q', 'Q', 'quit'):
            window.Close()
            return 'quit', None, None

        #-- Select trial
        elif event in ('g', 'G', 'choose_trial'):
            window.Close()
            return 'choose_trial', None, None

        #-- Open settings window
        elif event in ('e', 'E', 'settings'):
            window.Close()
            return 'settings', None, None

        #-- OK - Accept current coding
        if event in ('a', 'A', 'accept'):
            trial.rc = trial.stimulus
            if trial.response == (None or ""):
                sg.Popup('No response entered', 'Please enter a response with exactly {:} characters.'.format(len(on_paper_chars)))
            elif len(trial.response)!= len(on_paper_chars):
                sg.Popup('Unmatch number of characters', 'Please enter a response with exactly {:} characters.'.format(len(on_paper_chars)))
            else:
                save_trial(trial, characters, sub_trial_num, out_dir)
                window.Close()
                return 'next_trial', None, None


            '''if trial.response == (None or ""):
                text = sg.popup_get_text('Response', 'Please enter response:')
                if type(text) != None:
                    if len(text) != len(on_paper_chars):
                        sg.Popup('Unmatch number of characters', 'Please enter a response with exactly {:} characters.'.format(len(on_paper_chars)))
                    else:
                        trial.response = text
                        window.Close()
                        return 'next_trial', None, None'''



        #-- Clicked on DropDown error



        #-- Error - Accept current coding, set trial as error
        if event in ('o', 'O', 'accept_error'):
            trial.rc = values[0]
            save_trial(trial, characters, sub_trial_num, out_dir)
            if trial.response == (None or ""):
                sg.Popup('No response entered', 'Please enter a response')
            else:
                window.Close()
                return 'next_trial', None, None

        #-- Skip this trial
        elif event in ('k', 'K', 'skip_trial'):
            window.Close()
            return 'next_trial', None, None

        #-- Return to previous trial
        elif event in ('p', 'P', 'prev_trial'):
            window.Close()
            return 'prev_trial', None, None

        #-- Merge 2 characters
        elif event in ('m', 'M', 'merge_chars'):
            if current_command is None:
                instructions.Update('Select the characters to merge. ENTER=confirm, ESC=abort')
                current_command = 'merge_chars'
                if selection_handler is not None:
                    selection_handler = _CharSelector(graph, characters, 'any', selection_handler.selected)
                else:
                    selection_handler = _CharSelector(graph, characters, 'any', [])



        #-- Split a stroke into 2 characters
        elif event in ('s', 'S', 'split_stroke'):
            if current_command is None:
                instructions.Update('Select a stroke to split. ENTER=confirm, ESC=abort')
                current_command = 'split_stroke'
                selection_handler = _SingleStrokeSelector(graph, strokes)

        #-- Split a character
        elif event in ('c', 'C', 'split_char'):
            if current_command is None:
                instructions.Update('Select a character to split to 2 different characters. ENTER=confirm, ESC=abort')
                current_command = 'split_char'
                selection_handler = _MultiStrokeSelector(graph, characters)

        #-- Split the trial into 2 trials
        elif event in ('t', 'T', 'split_trial'):
            if current_command is None:
                instructions.Update('Select the last character of trial#1. ENTER=confirm, ESC=abort')
                current_command = 'split_trial'
                selection_handler = _CharSelector(graph, characters, 'series', None)


        #-- Self correction
        elif event in ('f', 'F', 'self_correction'):
            if current_command is None:
                instructions.Update('Select the correct character. ENTER=confirm, ESC=abort')
                window['show_correction'].update(disabled=True)
                current_command = 'self_correction'
                trial.self_correction = "1"
                selection_handler = _SingleStrokeSelector(graph, strokes)

                last_selection_handler = selection_handler

        # -- Show Self correction
        elif event == 'show_correction':
            #window['show_correction'].enable_events=True
            current_command = 'show_correction'
            chars1 = _self_correction(characters, last_selection_handler, window['show_correction'], current_command, values, graph)

            if (window['show_correction']).Get():
                window['show_correction'].Update(value=True)
            else:
                window['show_correction'].Update(value=False)
            window.Close()
            return 'show_correction', chars1, last_selection_handler


        # elif event == 'radio':
        #     current_command = 'show_correction'
        #     chars1 = _self_correction(characters, last_selection_handler, window['radio'], current_command, values, graph)
        #     window.Close()
        #     return 'show_correction', chars1, last_selection_handler
        #
        # elif event == 'radio2':
        #     current_command = 'show_correction'
        #     chars1 = _self_correction(characters, last_selection_handler, window['radio2'], current_command, values, graph)
        #     window.Close()
        #     return 'show_correction', chars1, last_selection_handler


        elif event == 'delete_stroke':
            if current_command is None:
                instructions.Update('Select a stroke to delete. ENTER=confirm, ESC=abort')
                current_command = 'delete_stroke'
                selection_handler = _SingleStrokeSelector(graph, strokes)

        elif event == 'response':
            text = sg.popup_get_text('Response', 'Please enter response:')
            trial.response = text
            window.Close()
            return 'response', characters, None

        #-- Mouse click
        elif event == 'graph':
            if selection_handler is not None:
                selection_handler.clicked(values)

        #-- ENTER clicked: end the currently-running command
        elif current_command is not None and len(event) == 1 and ord(event) == 13:
            if current_command == 'split_char':
                characters = _apply_split_character(characters, selection_handler)
                window.Close()
                return 'continue', characters, None

            elif current_command == 'merge_chars':
                if len(selection_handler.selected) < 2:
                    sg.Popup("Merge error", "Please select 2 or more characters")
                else:
                    characters = _apply_merge_characters_updated(characters, selection_handler)
                    window.Close()
                    return 'continue', characters, None

            elif current_command == 'split_stroke':
                window.Close()
                return 'split_stroke', characters, selection_handler.selected

            elif current_command == 'split_trial':
                chars1, chars2 = _split_chars_into_2_trials(characters, selection_handler)
                window.Close()
                return 'split_trial', chars1, chars2

            elif current_command == 'self_correction':
                chars1 = _self_correction(characters, selection_handler, window['self_correction'], current_command,values, graph)
                _set_stroke_color(last_selection_handler.selected, 'yellow', graph)
                window.Close()
                return 'self_correction', chars1, last_selection_handler

            elif current_command == 'delete_stroke':
                updated_characters = _delete_stroke(characters, selection_handler)
                window.Close()
                return 'delete_stroke', updated_characters, selection_handler.selected

            else:
                raise Exception('Bug')

        #-- ESC clicked: cancel the currently-running command
        #elif len(event) == 1 and ord(event) == 27:                         #Original line!!!
        if current_command is not None and len(event) == 1 and ord(event) == 27:
            instructions.Update('')
            current_command = None
            #if selection_handler is not None:
            selection_handler.cleanup()
            selection_handler = None


        #-- Just for debug
        else:
            if len(event) == 1:
                print("Clicked #{:}".format(ord(event)))
            instructions.Update('UNKNOWN COMMAND')


#-------------------------------------------------------------------------------------
def _create_window_for_markup(screen_size, title):

    commands_m = [
        sg.Text('Manipulations: '),
        sg.Button('Split (S)troke', key='split_stroke'),
        sg.Button('Split (C)haracter', key='split_char'),
        sg.Button('Split (T)rial', key='split_trial'),
        sg.Button('(M)erge 2 characters', key='merge_chars'),
        sg.Button('(R)eset current trial', key='reset_trial'),
        sg.Button('Sel(f) correction', key='self_correction'),
        sg.Checkbox('Show correction', key='show_correction', enable_events= True, disabled = True),
        sg.Button('Delete stroke', key='delete_stroke'),
        #sg.Radio('Show radio', key = 'radio', default=True, disabled= False,group_id=1,enable_events = True),
        #sg.Radio('Show radio2', key='radio2', default=True, disabled=False, group_id=1,enable_events = True),
    ]

    commands_nav = [
        sg.Text('Navigation / decision: '),
        sg.Button('(A)ccept as OK', key='accept'),
        sg.Button('Err(o)r:', key='accept_error'),
        sg.DropDown(markup_config['error_codes'], readonly=True),
        sg.Button('s(K)ip current trial', key='skip_trial'),
        sg.Button('(P)revious trial', key='prev_trial'),
        sg.Button('(G)o to specific trial', key='choose_trial'),
        sg.Button('Enter response', key='response'),
        #sg.Txt('Enter response:'),
        #sg.Input(key = 'text_response', enable_events= True),
    ]

    commands_general = [
        sg.Button('S(E)ttings', key='settings'),
        sg.Button('(Q)uit encoder', key='quit'),
    ]

    layout = [
        [sg.Text(' ' * 100, text_color='green', key='instructions', font=('Arial', 16))],
        [sg.Graph(screen_size, (0, screen_size[1]), (screen_size[0], 0), background_color='Black', key='graph', enable_events=True)],
        commands_m,
        commands_nav,
        commands_general
    ]


    label = tk.Label(text="Hello, Tkinter", fg="white", bg="yellow")
    label.pack()

    window = sg.Window(title, layout, return_keyboard_events=True)
    window.Finalize()

    return window


#-------------------------------------------------------------------------------------
def _plot_dots_for_markup(characters, graph, screen_size, expand_ratio, offset, margin, dot_radius):

    dot_num = 0
    char_index = 0
    for char in characters:
        char_index += 1
        strokes = char.on_paper_strokes

        color = RED if char.char_num % 2 == 1 else CYAN

        for i in range(len(strokes)):
            stroke = strokes[i]
            stroke.color = color[i] if i < len(color) else color[-1]

            for dot in stroke.trajectory:
                x = (dot.x - offset[0]) * expand_ratio + margin
                y = (dot.y - offset[1]) * expand_ratio + margin
                y = screen_size[1] - y
                dot.screen_x = x
                dot.screen_y = y
                dot.ui = graph.TKCanvas.create_oval(x - dot_radius, y - dot_radius, x + dot_radius, y + dot_radius, fill=stroke.color)
                dot_num = dot_num + 1
                #print("x is: " + str(x))
                #print("y is: " + str(y))
                #print("i is: " + str(i))


            graph.TKCanvas.create_text(x+2 , y+2 , fill='yellow', text=str(char_index) + "." + str(i+1), anchor = NW)

    '''self.canvas = Canvas(root, width=800, height=650, bg='#afeeee')
            self.canvas.create_text(100, 10, fill="darkblue", font="Times 20 italic bold",
                                    text="Click the bubbles that are multiples of two.")'''

    '''greeting = tk.Label(text="Hello, Tkinter")
            greeting.pack()
            #graph.mainloop()'''

    '''label = tk.Label(text="Hello, Tkinter", fg="white", bg="yellow")
            label.pack()'''

RED = ["#FF0000", "#FF8080", "#FFA0A0"]
CYAN = ["#00FFFF", "#A0FFFF", "#C0FFFF"]


#-------------------------------------------------------------------------------------
def _split_stroke(stroke, screen_size, margin, dot_radius=6):

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

        elif len(event) == 1 and ord(event) == 27:
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

    window = sg.Window('Split a stroke into 2', layout, return_keyboard_events=True)
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
            uidot = _DotForSplit(dot, color)

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
class _DotForSplit(object):

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
class _Dot(object):

    def __init__(self, dot):
        self.dot = dot

    @property
    def x(self):
        return self.dot.x

    @property
    def y(self):
        return self.dot.y

    @property
    def z(self):
        return self.dot.z

    @property
    def t(self):
        return self.dot.t


#-------------------------------------------------------------------------------------
class _Stroke(data.Stroke):

    def __init__(self, dots, stroke_num, on_paper):
        super().__init__(on_paper, None, dots)
        self.stroke_num = stroke_num
        self.is_seen = True
        # self.correction = correction

    @property
    def xlim(self):
        x = [d.x for d in self.trajectory]
        return min(x), max(x)

#-------------------------------------------------------------------------------------
class _Character(object):

    def __init__(self, char_num, strokes, correction):
        self.char_num = char_num
        self.strokes = strokes
        self.correction = correction

    @property
    def on_paper_strokes(self):
        return [s for s in self.strokes if s.on_paper]

    @property
    def on_paper_dots(self):
        return [d for stroke in self.on_paper_strokes for d in stroke]

    @property
    def trajectory(self):
        return [d for stroke in self.strokes for d in stroke]


#-------------------------------------------------------------------------------------
class _SingleStrokeSelector(object):
    """
    Handles click to select one stroke
    """

    def __init__(self, graph, strokes):
        self.graph = graph
        self.strokes = [s for s in strokes if len(s.trajectory) > 0]
        self.selected = None


    def clicked(self, values):

        click_coord = values['graph']
        if click_coord[0] is None:
            return

        clicked_stroke = _find_clicked_stroke(self.strokes, click_coord)        #finds the selected stroke

        if clicked_stroke == self.selected:             #second click on the same stroke
            self.cleanup()
            self.selected = None
        else:
            self.cleanup()                                  #clean previous stroke color
            self.selected = clicked_stroke
            self.highlight_selected()                       #colors the selected stroke


    def highlight_selected(self):
        _set_stroke_color(self.selected, "#00FF00", self.graph)


    def cleanup(self):
        if self.selected is not None:
            _set_stroke_color(self.selected, None, self.graph)



#-------------------------------------------------------------------------------------
class _MultiStrokeSelector(object):
    """
    Handles click to split a character into two sets of strokes
    """

    def __init__(self, graph, characters):
        self.graph = graph
        self.characters = [c for c in characters if len(c.on_paper_dots) > 0]
        self.strokes = [s for c in characters for s in c.on_paper_strokes]
        self.selected_stroke = None
        self.selected_char = None


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

        self.selected_stroke = _find_clicked_stroke(self.selected_char.on_paper_strokes, click_coord)
        self.highlight_selected()


    def highlight_selected(self):
        if self.selected_stroke != self.selected_char.strokes[-1]:
            strokes_to_highlight = [s for s in self.selected_char.on_paper_strokes if s.stroke_num <= self.selected_stroke.stroke_num]
        else:
            strokes_to_highlight = [self.selected_stroke]

        for s in strokes_to_highlight:
            _set_stroke_color(s, "#00FF00", self.graph)


    def cleanup(self):
        if self.selected_stroke is None:
            return

        for c in self.strokes:
            _set_stroke_color(c, None, self.graph)

#-------------------------------------------------------------------------------------


class _CharSelector(object):
    """
    Handles click to select one character
    """

    def __init__(self, graph, characters, mode, selected):
        assert mode in ('pair', 'series', 'any')
        self.graph = graph
        self.characters = [c for c in characters if len(c.on_paper_dots) > 0]
        self.mode = mode
        self.selected = selected


    def clicked(self, values):
        click_coord = values['graph']
        if click_coord[0] is None:
            return

        clicked_char = _find_clicked_char(self.characters, click_coord)


        if self.mode == 'any':
            if clicked_char in self.selected:
                self.unselect_cleanup(clicked_char)
                self.selected.remove(clicked_char)
            else:
                self.selected.append(clicked_char)
                self.highlight_selected()
        else:
            if clicked_char == self.characters[-1]:
                clicked_char = self.characters[-2]
            self.cleanup()
            self.selected = clicked_char
            self.highlight_selected()


    def highlight_selected(self):
        if self.mode == 'series':
            selected_num = self.selected.char_num
            chars_to_highlight = [c for c in self.characters if c.char_num <= selected_num]
        elif self.mode == 'pair':
            selected_num = self.selected.char_num
            chars_to_highlight = [c for c in self.characters if selected_num <= c.char_num <= selected_num + 1]
        elif self.mode == 'any':
            chars_to_highlight = [c for c in self.characters if c in self.selected]
        else:
            raise Exception('Bug')

        for c in chars_to_highlight:
            _set_char_color(c, "#00FF00", self.graph)


    def cleanup(self):
        if self.selected is None:
            return
        for c in self.characters:
            _set_char_color(c, None, self.graph)

    def unselect_cleanup(self, clicked_char):
        if clicked_char is not None:
            _set_char_color(clicked_char, None, self.graph)


#-------------------------------------------------------------------------------------
def _create_default_characters(dots, max_within_char_overlap):
    """
    Create characters in a default manner: each stroke is a separate character, but horizontally-overlapping strokes
    are separate characters
    """

    strokes = _split_dots_into_strokes(dots)

    characters = []
    curr_char = None
    curr_char_has_on_paper_strokes = False
    correction = 0

    for stroke in strokes:

        if curr_char is None:
            #-- First stroke in a the number: always in the first character
            create_new_char = True
        elif not stroke.on_paper or not curr_char_has_on_paper_strokes:
            create_new_char = False
        else:
            create_new_char = len(stroke.trajectory) == 0 or _x_overlap_ratio(curr_char.on_paper_dots, stroke.trajectory) < max_within_char_overlap

        if create_new_char:
            curr_char = _Character(len(characters) + 1, [stroke], correction)
            curr_char_has_on_paper_strokes = stroke.on_paper
            characters.append(curr_char)
        else:
            curr_char.strokes.append(stroke)
            curr_char_has_on_paper_strokes = curr_char_has_on_paper_strokes or stroke.on_paper

    return characters


#-------------------------------------------------------------------------------------
def _split_dots_into_strokes(dots):

    strokes = []

    curr_stroke_dots = []
    curr_stroke_num = 1
    prev_on_paper = False
    correction = 0

    for dot in dots:

        on_paper = dot.z > 0

        if prev_on_paper != on_paper:
            #-- Pen lifted from paper or put on it
            curr_stroke_num += 1
            strokes.append(_Stroke(curr_stroke_dots, curr_stroke_num, prev_on_paper))
            curr_stroke_dots = []

        curr_stroke_dots.append(_Dot(dot))
        prev_on_paper = on_paper

    strokes.append(_Stroke(curr_stroke_dots, curr_stroke_num + 1, prev_on_paper))

    return strokes


#-------------------------------------------------------------------------------------
def _x_overlap_ratio(dots1, dots2):
    """
    Get 2 arrays of dots and return the % of overlap between the two intervals.
    The overlap is defined as: overlapping_inverval / total_inverval
    """

    x1 = [d.x for d in dots1]
    x2 = [d.x for d in dots2]

    max1 = max(x1)
    min1 = min(x1)
    max2 = max(x2)
    min2 = min(x2)

    overlap = min(max1, max2) - max(min1, min2)
    overlap = max(overlap, 0)

    total_width = max(max1, max2) - min(min1, min2)

    if total_width == 0:
        return 1
    else:
        return overlap / total_width


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
def _apply_split_character(characters, selection_handler):

    char = selection_handler.selected_char
    char_ind = characters.index(char)

    stroke = selection_handler.selected_stroke

    if stroke == char.on_paper_strokes[-1]:
        last_char1_stroke_num = stroke.stroke_num - 1
    else:
        last_char1_stroke_num = stroke.stroke_num

    char1_strokes = [s for s in char.strokes if s.stroke_num <= last_char1_stroke_num]
    char2_strokes = [s for s in char.strokes if s.stroke_num > last_char1_stroke_num]

    correction = stroke.correction
    char1 = _Character(char.char_num, char1_strokes, correction)
    char2 = _Character(char.char_num + 1, char2_strokes, correction)

    #-- Remove the chara that was split
    characters.pop(char_ind)

    characters.insert(char_ind, char2)
    characters.insert(char_ind, char1)

    _renumber_chars_and_strokes(characters)

    return characters


#---------------------------------------------------------------------------------------
def _renumber_chars_and_strokes(characters):

    '''if current_command == 'delete_stroke':
        for i in range(len(characters)):
            char = characters[i]
            for j in range(len(char.strokes)):
                char.strokes[j].stroke_num = j - 1'''

    for i in range(len(characters)):
        char = characters[i]
        char.char_num = i + 1
        for j in range(len(char.strokes)):
            char.strokes[j].stroke_num = j + 1

#-------------------------------------------------------------------------------------
def _apply_merge_characters_updated(characters, selection_handler):

    on_pen_chars = [c for c in characters if len(c.trajectory) > 0]
    char1 = selection_handler.selected[0]
    char1_ind = on_pen_chars.index(char1)

    if char1_ind == len(on_pen_chars) - 1:
        char1_ind -= 1
        char1 = on_pen_chars[char1_ind]

    for i in range(1, len(selection_handler.selected)):
        selected_char_index = on_pen_chars.index(selection_handler.selected[i])
        selected_char = selection_handler.selected[i]

        correction = max(char1.correction, selected_char.correction)

        merged_char = _Character(char1_ind, char1.strokes + selected_char.strokes, correction)

        char1_ind = characters.index(char1)
        characters[char1_ind] = merged_char
        char1 = merged_char
        characters.remove(on_pen_chars[selected_char_index])

    _renumber_chars_and_strokes(characters)

    return characters



#-------------------------------------------------------------------------------------
def _apply_merge_characters_old(characters, selection_handler):

    on_pen_chars = [c for c in characters if len(c.trajectory) > 0]
    char1 = selection_handler.selected
    char1_ind = on_pen_chars.index(char1)

    if char1_ind == len(on_pen_chars) - 1:
        char1_ind -= 1
        char1 = on_pen_chars[char1_ind]

    char2 = on_pen_chars[char1_ind + 1]

    correction = max(char1.correction, char2.correction)

    merged_char = _Character(char1_ind, char1.strokes + char2.strokes, correction)

    char1_ind = characters.index(char1)
    characters[char1_ind] = merged_char
    characters.remove(char2)

    _renumber_chars_and_strokes(characters)

    return characters


#-------------------------------------------------------------------------------------
def _split_chars_into_2_trials(characters, selection_handler):

    on_pen_chars = [c for c in characters if len(c.trajectory) > 0]
    trial1_last_char = selection_handler.selected
    char_ind = on_pen_chars.index(trial1_last_char)

    if char_ind == len(on_pen_chars) - 1:
        char_ind -= 1
        trial1_last_char = on_pen_chars[char_ind]

    trial1_chars = [c for c in characters if c.char_num <= trial1_last_char.char_num]
    trial2_chars = [c for c in characters if c.char_num > trial1_last_char.char_num]

    return trial1_chars, trial2_chars


#-------------------------------------------------------------------------------------
def _apply_split_stroke(characters, stroke, dot):

    if dot == stroke.trajectory[-1]:
        # Nothing to split
        return characters

    char = [c for c in characters if stroke in c.strokes]
    assert len(char) == 1
    char = char[0]
    char_ind = characters.index(char)

    dot_ind = stroke.trajectory.index(dot)

    correction = stroke.correction


    dots1 = stroke.trajectory[:dot_ind+1]
    dots2 = stroke.trajectory[dot_ind+1:]

    stroke1 = _Stroke(dots1, 0, True)
    stroke2 = _Stroke(dots2, 0, True)

    stroke_ind = char.strokes.index(stroke)

    char1_strokes = char.strokes[:stroke_ind]
    char1_strokes.append(stroke1)
    char1 = _Character(0, char1_strokes,correction)

    char2_strokes = char.strokes[stroke_ind+1:]
    char2_strokes.insert(0, stroke2)
    char2 = _Character(0, char2_strokes, correction)

    characters = list(characters)
    characters[char_ind] = char1
    characters.insert(char_ind+1, char2)

    _renumber_chars_and_strokes(characters)

    return characters


#-------------------------------------------------------------------------------------
def save_trial(trial, characters, sub_trial_num, out_dir):

    dataio.append_to_trial_index(out_dir, trial.trial_id, sub_trial_num, trial.target_id, trial.stimulus,
                                            trial.response, trial.time_in_session, trial.rc, trial.self_correction, trial.sound_file_length)

    strokes = []
    for c in characters:
        trial.self_correction = c.correction
        for stroke in c.strokes:
            stroke.char_num = c.char_num

        if not c.strokes[0].on_paper:
            c.strokes[0].char_num = 0

        if not c.strokes[-1].on_paper:
            c.strokes[-1].char_num = 0

        strokes.extend(c.strokes)


    dataio.save_trajectory(strokes, trial.trial_id, sub_trial_num, out_dir, trial)
    dataio.save_strokes_file(strokes, trial.trial_id, sub_trial_num, out_dir, trial)
    dataio.save_characters_file(characters, strokes, trial.trial_id, sub_trial_num, out_dir, trial)


#-------------------------------------------------------------------------------------

def _self_correction(characters, selection_handler, checkbox, current_command, values, graph):
    test_char = characters
    if current_command == 'show_correction':
        if(checkbox.Get()):                               #Checkbox function
        #if values['radio'] == True:
            if(values['show_correction'] == False):
                for c in test_char:
                    for s in c.strokes:
                        if s == selection_handler.selected:
                            s.on_paper = True
        else:
            #if values['radio2'] == True:
            for c in test_char:
                for s in c.strokes:
                    if s == selection_handler.selected:
                        s.on_paper = False

    else:                                                   #Self correction button function
        for c in test_char:
            for s in c.strokes:
                if s == selection_handler.selected:
                    s.on_paper = True
                    #_set_stroke_color(s, 'yellow', graph)
                    s.correction = 1
                    c.correction = 1

    return test_char

def _delete_stroke(characters, selection_handler):
    test_char = characters
    #updated_characters = test_char
    for c in test_char:
        for s in c.strokes:
            if s == selection_handler.selected:
                if len(c.on_paper_strokes) > 1:                  #Check if the character has more than 1 stroke. Else error.
                    c.strokes.remove(s)
                else:
                    sg.Popup('Char has only 1 stroke', 'Choose a Character with more than 1 stroke')
                    break

    return test_char

                                #updated_characters = c for c in characters if c.char_num <= trial1_last_char.char_num
