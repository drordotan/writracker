import unittest
from collections import namedtuple

from writracker.encoder.manip import delete_stroke
from writracker.encoder.trialcoder import UiStroke, UiCharacter, UiTrajPoint


#----------------------------------------------------------------

DummyDot = namedtuple('DummyDot', ['x', 'y', 'z', 't'])
dummy_dot = DummyDot(0, 0, 0, 0)


#----------------------------------------------------------------
def create_chars(config):

    # P = on_paper_stroke
    # S = space_stroke

    characters = []

    for ci, conf_item in enumerate(config):
        strokes = [MyUiStroke(ci + 1, si + 1, s == 'P') for si, s in enumerate(conf_item)]
        item = UiCharacter(ci+1, strokes)
        characters.append(item)

    return characters


#----------------------------------------------------------------
class DummySelectionHandler(object):

    def __init__(self, characters, char_num, stroke_num):
        self.selected = characters[char_num].strokes[stroke_num]


#----------------------------------------------------------------
class MyUiStroke(UiStroke):

    def __init__(self, char_num, stroke_num, on_paper):
        super().__init__([UiTrajPoint(dummy_dot)], stroke_num, on_paper)
        self.char_num = char_num

    @property
    def id(self):
        return "{}.{}".format(self.char_num, self.stroke_num)


#----------------------------------------------------------------
def char_strokes(char):
    on_paper = ['P' if s.on_paper else 'S' for s in char.strokes]
    return ''.join(on_paper)


#===========================================================================================================
class DeleteStrokeTests(unittest.TestCase):

    #----------------------------------------------------------------
    def _validate_char_and_stroke_nums(self, characters):

        for i_char, char in enumerate(characters):
            self.assertEquals(i_char+1, char.char_num)
            for i_stroke, stroke in enumerate(char.strokes):
                self.assertEquals(i_char+1, stroke.char_num)
                self.assertEquals(i_stroke+1, stroke.stroke_num)


    #----------------------------------------------------------------
    def test_delete_first_stroke_in_trial(self):

        chars = create_chars(['PSPS', 'PSP', 'PS'])
        #  Deleting this:      ^
        #  Expected result: merge with the following space

        new_chars, err_msg = delete_stroke(chars, DummySelectionHandler(chars, 0, 0))

        self.assertEquals(3, len(new_chars))
        if len(new_chars) != 3:
            return

        c0, c1, c2 = chars

        self.assertEquals('SPS', char_strokes(c0))
        self.assertEquals('PSP', char_strokes(c1))
        self.assertEquals('PS', char_strokes(c2))

        if len(c0.strokes) == 3:
            self.assertEquals(2, len(c0.strokes[0].trajectory))
            self.assertEquals(1, len(c0.strokes[1].trajectory))
            self.assertEquals(1, len(c0.strokes[2].trajectory))

        self._validate_char_and_stroke_nums(chars)


    #----------------------------------------------------------------
    def test_delete_first_stroke_in_trial_after_space(self):

        chars = create_chars(['SPSPS', 'PSP', 'PS'])
        #  Deleting this:       ^
        #  Expected result: merge with the preceding&following space

        new_chars, err_msg = delete_stroke(chars, DummySelectionHandler(chars, 0, 1))

        self.assertEquals(3, len(new_chars))
        if len(new_chars) != 3:
            return

        c0, c1, c2 = chars

        self.assertEquals('SPS', char_strokes(c0))
        self.assertEquals('PSP', char_strokes(c1))
        self.assertEquals('PS', char_strokes(c2))

        if len(c0.strokes) == 3:
            self.assertEquals(3, len(c0.strokes[0].trajectory))
            self.assertEquals(1, len(c0.strokes[1].trajectory))
            self.assertEquals(1, len(c0.strokes[2].trajectory))

        self._validate_char_and_stroke_nums(chars)


    #----------------------------------------------------------------
    def test_delete_first_stroke_in_2nd_char(self):

        chars = create_chars(['PSPS', 'PSP', 'PS'])
        #  Deleting this:              ^
        #  Expected result: merge with the following space, and with the space at the end of the previous character

        new_chars, err_msg = delete_stroke(chars, DummySelectionHandler(chars, 1, 0))

        self.assertEquals(3, len(new_chars))
        if len(new_chars) != 3:
            return

        c0, c1, c2 = chars

        self.assertEquals('PSPS', char_strokes(c0))
        self.assertEquals('P', char_strokes(c1))
        self.assertEquals('PS', char_strokes(c2))

        self._validate_char_and_stroke_nums(chars)

        self.assertEquals(3, len(c0.strokes[3].trajectory))


    #----------------------------------------------------------------
    def test_delete_last_stroke_in_char(self):

        chars = create_chars(['PSP', 'PSP', 'PS'])
        #  Deleting this:        ^
        #  Expected result: merge with the preceding space

        new_chars, err_msg = delete_stroke(chars, DummySelectionHandler(chars, 0, 2))

        self.assertEquals(3, len(new_chars))
        if len(new_chars) != 3:
            return

        c0, c1, c2 = chars

        self.assertEquals('PS', char_strokes(c0))
        self.assertEquals('PSP', char_strokes(c1))
        self.assertEquals('PS', char_strokes(c2))

        self._validate_char_and_stroke_nums(chars)

        self.assertEquals(1, len(c0.strokes[0].trajectory))
        self.assertEquals(2, len(c0.strokes[1].trajectory))


    #----------------------------------------------------------------
    def test_delete_last_stroke_in_char_before_space(self):

        chars = create_chars(['PSPS', 'PSP', 'PS'])
        #  Deleting this:        ^
        #  Expected result: merge with the preceding space

        new_chars, err_msg = delete_stroke(chars, DummySelectionHandler(chars, 0, 2))

        self.assertEquals(3, len(new_chars))
        if len(new_chars) != 3:
            return

        c0, c1, c2 = chars

        self.assertEquals('PS', char_strokes(c0))
        self.assertEquals('PSP', char_strokes(c1))
        self.assertEquals('PS', char_strokes(c2))

        self._validate_char_and_stroke_nums(chars)

        self.assertEquals(1, len(c0.strokes[0].trajectory))
        self.assertEquals(3, len(c0.strokes[1].trajectory))


    #----------------------------------------------------------------
    def test_delete_mid_stroke_in_char(self):

        chars = create_chars(['PSP', 'PSPSP', 'PS'])
        #  Deleting this:               ^
        #  Expected result: merge with the preceding&following space

        new_chars, err_msg = delete_stroke(chars, DummySelectionHandler(chars, 1, 2))

        self.assertEquals(3, len(new_chars))
        if len(new_chars) != 3:
            return

        c0, c1, c2 = chars

        self.assertEquals('PSP', char_strokes(c0))
        self.assertEquals('PSP', char_strokes(c1))
        self.assertEquals('PS', char_strokes(c2))

        self._validate_char_and_stroke_nums(chars)

        self.assertEquals(1, len(c1.strokes[0].trajectory))
        self.assertEquals(3, len(c1.strokes[1].trajectory))
        self.assertEquals(1, len(c1.strokes[2].trajectory))


    #----------------------------------------------------------------
    def test_single_stroke_in_char(self):

        chars = create_chars(['PSP', 'SPS', 'PS'])
        #  Deleting this:              ^
        #  Expected result: character deleted

        new_chars, err_msg = delete_stroke(chars, DummySelectionHandler(chars, 1, 1))

        self.assertEquals(2, len(new_chars))

        if len(new_chars) != 2:
            return

        c0, c1 = chars

        self.assertEquals('PSPS', char_strokes(c0))
        self.assertEquals('PS', char_strokes(c1))

        self._validate_char_and_stroke_nums(chars)

        self.assertEquals(1, len(c0.strokes[0].trajectory))
        self.assertEquals(1, len(c0.strokes[1].trajectory))
        self.assertEquals(1, len(c0.strokes[2].trajectory))
        self.assertEquals(3, len(c0.strokes[3].trajectory))


    #----------------------------------------------------------------
    def test_single_stroke_in_char_with_space_ending_previous_char(self):

        chars = create_chars(['PS', 'SPS', 'PS'])
        #  Deleting this:             ^
        #  Expected result: merge with the preceding&following space

        new_chars, err_msg = delete_stroke(chars, DummySelectionHandler(chars, 1, 1))

        self.assertEquals(2, len(new_chars))
        if len(new_chars) != 2:
            return

        c0, c1 = chars

        self.assertEquals('PS', char_strokes(c0))
        self.assertEquals('PS', char_strokes(c1))

        self._validate_char_and_stroke_nums(chars)

        self.assertEquals(1, len(c0.strokes[0].trajectory))
        self.assertEquals(4, len(c0.strokes[1].trajectory))


if __name__ == '__main__':
    unittest.main()
