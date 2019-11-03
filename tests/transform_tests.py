import unittest
import random

from writracker.analyze.transform import find_interval_containing, get_bounding_box
from writracker.data import TrajectoryPoint



def make_trajectory(points):
    return [TrajectoryPoint(pt[0], pt[1], 0, 0) for pt in points]

class DummyStroke(object):
    def __init__(self, trajectory):
        self.trajectory = trajectory
        self.on_paper = True

class DummyChar(object):
    def __init__(self, trajectory):
        self.strokes = [DummyStroke(trajectory)]


class GetBoundingBoxTests(unittest.TestCase):

    #----------------------------------------------------------------------------
    def test_find_interval_containing_all_values(self):
        s, e = find_interval_containing([9, 5, 10, 1, 3, 8], 1, True)
        self.assertEqual(1, s)
        self.assertEqual(10, e)

    #----------------------------------------------------------------------------
    def test_find_interval_containing_all_values_2(self):
        s, e = find_interval_containing([9, 5, 10, 1, 3, 8, 1], 1, False)
        self.assertEqual(1, s)
        self.assertEqual(10, e)

    #----------------------------------------------------------------------------
    def test_find_interval_containing__p_must_be_positive(self):
        self.assertRaises(AssertionError, lambda: find_interval_containing([1, 2], 0))

    #----------------------------------------------------------------------------
    def test_find_interval_containing__p_must_be_up_to_1(self):
        find_interval_containing([1, 2], 1)
        self.assertRaises(AssertionError, lambda: find_interval_containing([1, 2], 1.000001))


    #----------------------------------------------------------------------------
    def test_find_interval_containing_some_values(self):
        values = [1, 2, 3, 4, 4.1, 4.9, 5, 6, 7, 10]
        random.shuffle(values)
        s, e = find_interval_containing(values, .4, False)
        self.assertEqual(4, s)
        self.assertEqual(5, e)


    #----------------------------------------------------------------------------
    def test_find_interval_containing_some_values_in_place(self):
        values = [1, 2, 3, 4, 4.1, 4.9, 5, 6, 7, 10]
        random.shuffle(values)
        s, e = find_interval_containing(values, .4, True)
        self.assertEqual(4, s)
        self.assertEqual(5, e)


    #----------------------------------------------------------------------------
    def test_find_interval_containing_returns_central_possibility__even(self):
        values = [0, 1, 2, 3, 4, 5, 6, 7]
        random.shuffle(values)
        for i in range(10):  # Trying 10 times to make sure the result is consistent
            s, e = find_interval_containing(values, .4, False)
            self.assertEqual(2, s)
            self.assertEqual(5, e)


    #----------------------------------------------------------------------------
    def test_find_interval_containing_returns_central_possibility__odd(self):
        values = [0, 1, 2, 3, 4, 5, 6, 7, 8]
        random.shuffle(values)
        for i in range(10):  # Trying 10 times to make sure the result is consistent
            s, e = find_interval_containing(values, .4, False)
            self.assertEqual(2, s)
            self.assertEqual(5, e)


    #----------------------------------------------------------------------------
    def test_get_bounding_box(self):
        trajectory = make_trajectory([(1, 10), (5, 6), (4, 2)])
        x, w, y, h, xmin, ymin = get_bounding_box(DummyChar(trajectory))
        self.assertEqual(3, x)
        self.assertEqual(4, w)
        self.assertEqual(6, y)
        self.assertEqual(8, h)
        self.assertEqual(1, xmin)
        self.assertEqual(2, ymin)



if __name__ == '__main__':
    unittest.main()
