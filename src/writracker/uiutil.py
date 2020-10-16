import re
import os

import tkinter as tk
from tkinter import filedialog, messagebox
import PySimpleGUI as sg


#---------------------------------------------------------------------
def screen_size():

    root = tk.Tk()
    width = root.winfo_screenwidth()
    height = root.winfo_screenheight()
    return width, height


#---------------------------------------------------------------------
def choose_directory(title='', initial_dir=None):
    if os.name == 'posix' and title is not None and title != '':
        messagebox.showinfo(title='Choose a directory', message=title)

    return filedialog.askdirectory(title=title, initialdir=initial_dir)


#---------------------------------------------------------------------
def choose_file(title=''):
    """
    Open a dialog to get a file name
    """
    root = tk.Tk()

    if os.name == 'posix' and title is not None and title != '':
        messagebox.showinfo(title)

    filename = filedialog.askopenfilename(title=title)
    root.update()

    return filename


#----------------------------------------------------------
def get_subject_id():

    show_popup = True
    warning = ' ' * 80
    subj_id = ''

    while show_popup:

        layout = [
            [sg.Text(warning, text_color='red', font=('Arial', 18))],
            [sg.Text('Subject ID: '), sg.InputText(subj_id)],
            [sg.Button('OK')],
        ]

        window = sg.Window('Choose trial', layout)

        event = None
        apply = False
        values = ()

        while event is None:
            event, values = window.Read()

        window.Close()

        subj_id = values[0]

        if re.match('[a-zA-Z0-9_&-]+]', subj_id):
            break

        warning = 'Invalid subject ID, please use only letters, digits, and valid characters (-_&)'

    return subj_id


