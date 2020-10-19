import numpy as np

from writracker.encoder import dataio


#=====================================================================================================
# Data objects
#=====================================================================================================

#-------------------------------------------------------------------------------------
class UiCharacter(object):
    """
    Represents a character in the application.
    Inter-character space strokes are appended to the preceding character.
    """

    def __init__(self, char_num, strokes, extends=None):
        self.char_num = char_num
        self.strokes = strokes
        self.extends = extends

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
class UiStroke(object):

    def __init__(self, traj_points, stroke_num, on_paper):
        self.on_paper = on_paper
        self.char_num = None
        self.trajectory = traj_points
        self.stroke_num = stroke_num

    @property
    def xlim(self):
        x = [d.x for d in self.trajectory]
        return min(x), max(x)

    def __iter__(self):
        return self.trajectory.__iter__()


#-------------------------------------------------------------------------------------
class UiTrajPoint(object):

    def __init__(self, dot):
        self.dot = dot
        self.ui = None

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


#=====================================================================================================
# Default grouping to character
#=====================================================================================================

#-------------------------------------------------------------------------------------
def create_default_characters(dots, max_within_char_overlap):
    """
    Create characters in a default manner: each stroke is a separate character, but horizontally-overlapping strokes
    are separate characters
    """

    strokes = _split_dots_into_strokes(dots)

    characters = []
    curr_char = None
    curr_char_has_on_paper_strokes = False

    for stroke in strokes:

        if curr_char is None:
            #-- First stroke in a the number: always in the first character
            create_new_char = True
        elif not stroke.on_paper or not curr_char_has_on_paper_strokes:
            #-- A not-on-paper stroke goes into the existing character
            create_new_char = False
        else:
            create_new_char = len(stroke.trajectory) == 0 or _x_overlap_ratio(curr_char.on_paper_dots, stroke.trajectory) < max_within_char_overlap

        if create_new_char:
            curr_char = UiCharacter(len(characters)+1, [stroke])
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

    for dot in dots:

        on_paper = dot.z > 5

        if prev_on_paper != on_paper:
            #-- Pen lifted from paper or put on it
            curr_stroke_num += 1
            strokes.append(UiStroke(curr_stroke_dots, curr_stroke_num, prev_on_paper))
            curr_stroke_dots = []

        curr_stroke_dots.append(UiTrajPoint(dot))
        prev_on_paper = on_paper

    strokes.append(UiStroke(curr_stroke_dots, curr_stroke_num+1, prev_on_paper))

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


#=====================================================================================================
# Split Trial
#=====================================================================================================

#-------------------------------------------------------------------------------------
def split_into_2_trials(characters, trial1_last_char):

    on_pen_chars = [c for c in characters if len(c.trajectory) > 0]
    char_ind = on_pen_chars.index(trial1_last_char)

    if char_ind == len(on_pen_chars) - 1:
        char_ind -= 1
        trial1_last_char = on_pen_chars[char_ind]

    trial1_chars = [c for c in characters if c.char_num <= trial1_last_char.char_num]
    trial2_chars = [c for c in characters if c.char_num > trial1_last_char.char_num]

    return trial1_chars, trial2_chars


#=====================================================================================================
# Split character
#=====================================================================================================

#-------------------------------------------------------------------------------------
def split_character(characters, char, stroke):

    if char is None:
        return characters

    char_ind = characters.index(char)

    if stroke == char.on_paper_strokes[-1]:
        last_char1_stroke_num = stroke.stroke_num - 1
    else:
        last_char1_stroke_num = stroke.stroke_num

    char1_strokes = [s for s in char.strokes if s.stroke_num <= last_char1_stroke_num]
    char2_strokes = [s for s in char.strokes if s.stroke_num > last_char1_stroke_num]

    char1 = UiCharacter(char.char_num, char1_strokes)
    char2 = UiCharacter(char.char_num+1, char2_strokes)

    #-- Remove the chara that was split
    characters.pop(char_ind)

    characters.insert(char_ind, char2)
    characters.insert(char_ind, char1)

    _renumber_chars_and_strokes(characters)

    return characters


#=====================================================================================================
# Extend character
#=====================================================================================================

#-------------------------------------------------------------------------------------
def set_extending_characters(all_chars, connected_chars):
    """
    Connect the given characters as "extending" the first among them
    """

    if len(connected_chars) <= 1:
        return

    base_char_num = min([c.char_num for c in connected_chars])

    #-- make sure 'selected_chars' extend the base char
    for c in connected_chars:
        if c.char_num != base_char_num:
            c.extends = base_char_num

    #-- make sure other chars don't extend the base char
    for c in all_chars:
        if c not in connected_chars and c.extends == base_char_num:
            c.extends = None


#-------------------------------------------------------------------------------------
def disconnect_extending_characters(connected_chars):
    """
    Get a list of characters connected as "extended", and disconnect them
    """

    if len(connected_chars) <= 1:
        return

    base_char_num = min([c.char_num for c in connected_chars])
    if sum([c.extends is not None and c.extends != base_char_num for c in connected_chars]) > 0:
        extended_values = list({c.extends for c in connected_chars})
        raise ValueError('WEncoder error ENC-DISC-EXT-001 (base={}, extending={})'.format(base_char_num, extended_values))

    for c in connected_chars:
        c.extends = None


#=====================================================================================================
# Merge character
#=====================================================================================================

#-------------------------------------------------------------------------------------
def merge_characters(characters,  char1):

    on_pen_chars = [c for c in characters if len(c.trajectory) > 0]
    if char1 not in on_pen_chars:
        raise Exception('WEncoder problem ENC-MERGE-001 (char_num={}, on_pen={})'.format(char1.char_num, [c.char_num for c in on_pen_chars]))
    char1_ind = on_pen_chars.index(char1)

    if char1_ind == len(on_pen_chars) - 1:
        char1_ind -= 1
        char1 = on_pen_chars[char1_ind]

    char2 = on_pen_chars[char1_ind + 1]

    merged_char = UiCharacter(char1_ind, char1.strokes + char2.strokes, extends=char1.extends)

    char1_ind = characters.index(char1)
    characters[char1_ind] = merged_char
    characters.remove(char2)

    _renumber_chars_and_strokes(characters)

    return characters


#=====================================================================================================
# Split stroke
#=====================================================================================================

#-------------------------------------------------------------------------------------
def split_stroke(characters, stroke, dot):

    if dot == stroke.trajectory[-1]:
        # Nothing to split
        return characters

    char = [c for c in characters if stroke in c.strokes]
    assert len(char) == 1
    char = char[0]
    char_ind = characters.index(char)

    dot_ind = stroke.trajectory.index(dot)

    dots1 = stroke.trajectory[:dot_ind+1]
    dots2 = stroke.trajectory[dot_ind+1:]

    stroke1 = UiStroke(dots1, 0, True)
    stroke2 = UiStroke(dots2, 0, True)

    stroke_ind = char.strokes.index(stroke)

    char1_strokes = char.strokes[:stroke_ind]
    char1_strokes.append(stroke1)
    char1 = UiCharacter(0, char1_strokes)

    char2_strokes = char.strokes[stroke_ind+1:]
    char2_strokes.insert(0, stroke2)
    char2 = UiCharacter(0, char2_strokes)

    characters = list(characters)
    characters[char_ind] = char1
    characters.insert(char_ind+1, char2)

    _renumber_chars_and_strokes(characters)

    return characters


#=====================================================================================================
# Delete stroke
#=====================================================================================================

#-------------------------------------------------------------------------------------
def delete_stroke(characters, selection_handler):

    if len(characters) == 1 and len(characters[0].strokes) == 1:
        return characters, 'You cannot delete the last character in the trial'

    deleted_stroke = selection_handler.selected

    if deleted_stroke not in [s for c in characters for s in c.strokes]:
        raise Exception('Deleted stroke was not found in this trial')

    deleted_char_ind = np.where([deleted_stroke in c.strokes for c in characters])[0][0]
    deleted_stroke_ind = characters[deleted_char_ind].strokes.index(deleted_stroke)

    _change_stroke_to_space(characters[deleted_char_ind], deleted_stroke_ind)
    _move_leading_space_to_prev_char(characters, deleted_char_ind)

    return characters, None


#-----------------------------------------------------------------------------------
def _change_stroke_to_space(char, deleted_stroke_ind):
    """
    Change the status of the stroke to be on_paper=False
    If the preceding/following strokes are space, merge them
    """

    deleted_stroke = char.strokes[deleted_stroke_ind]
    if not deleted_stroke.on_paper:
        raise Exception("Stroke #{}.{} cannot be deleted - it's already a deleted stroke".format(char.char_num, deleted_stroke_ind+1))

    deleted_stroke.on_paper = False

    #-- Merge with previous stroke if it's space
    stroke1_deleted = _merge_consecutive_space_strokes(char, deleted_stroke_ind - 1)
    if stroke1_deleted:
        deleted_stroke_ind -= 1

    #-- Merge with the subsequent stroke if it's space
    stroke2_deleted = _merge_consecutive_space_strokes(char, deleted_stroke_ind)

    if stroke1_deleted or stroke2_deleted:
        _renumber_strokes(char)


#-----------------------------------------------------------------------------------
def _merge_consecutive_space_strokes(char, stroke1_ind):
    """
    If two consecutive strokes are spaces: merge them.

    :param char:
    :param stroke1_ind: The index of the earlier stroke
    :return: True if strokes were merge (the 2nd one was deleted).
    """

    if 0 <= stroke1_ind < len(char.strokes) - 1 and not char.strokes[stroke1_ind].on_paper and not char.strokes[stroke1_ind+1].on_paper:
        char.strokes[stroke1_ind].trajectory.extend(char.strokes[stroke1_ind+1].trajectory)
        char.strokes.pop(stroke1_ind+1)
        return True

    else:
        return False


#-----------------------------------------------------------------------------------
def _renumber_chars_and_strokes(characters):
    for i, char in enumerate(characters):
        char.char_num = i+1
        for stroke in char.strokes:
            stroke.char_num = char.char_num


#-----------------------------------------------------------------------------------
def _renumber_strokes(char):
    for i, stroke in enumerate(char.strokes):
        stroke.stroke_num = i+1
        stroke.char_num = char.char_num


#-----------------------------------------------------------------------------------
def _move_leading_space_to_prev_char(characters, char_ind):
    """
    If the first stroke in the target character is space, move it to be the last stroke of the previous character.

    If the character remained empty, delete it.
    """

    if char_ind == 0:
        #-- No previous character before the first char
        return

    char = characters[char_ind]
    if char.strokes[0].on_paper:
        #-- the first stroke is on paper: no need to move
        return

    #-- Remove stroke from this char
    space_stroke = char.strokes[0]
    char.strokes.pop(0)
    if len(char.strokes) == 0:
        #-- No strokes remained
        characters.remove(char)
        _renumber_chars_and_strokes(characters)
    else:
        _renumber_strokes(char)

    #-- Add it to previous char
    prev_char = characters[char_ind-1]
    prev_char.strokes.append(space_stroke)

    _merge_consecutive_space_strokes(prev_char, len(prev_char.strokes) - 2)

    _renumber_strokes(prev_char)
