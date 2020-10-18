import numpy as np


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
    deleted_stroke.correction = False

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
def _renumber_characters(characters):
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
        _renumber_characters(characters)
    else:
        _renumber_strokes(char)

    #-- Add it to previous char
    prev_char = characters[char_ind-1]
    prev_char.strokes.append(space_stroke)

    _merge_consecutive_space_strokes(prev_char, len(prev_char.strokes) - 2)

    _renumber_strokes(prev_char)
