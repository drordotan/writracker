
import csv
from collections import namedtuple


#-------------------------------------------------------------------------------------------------
def load_trajectory(filename):
    """
    Load a raw trajectory file

    The file starts with name=value lines.
    Then, there must be a line saying "trajectory", followed by a CSV format
    """
    with open(filename, 'r') as fp:
        reader = csv.DictReader(fp)
        trajectory = []
        for line in reader:
            x = _parse_traj_value(line, 'x', reader.line_num, filename)
            y = _parse_traj_value(line, 'y', reader.line_num, filename)
            prs = _parse_traj_value(line, 'pressure', reader.line_num, filename)
            t = _parse_traj_value(line, 'time', reader.line_num, filename)
            pt = TrajectoryPoint(x, y, prs, t)
            trajectory.append(pt)

    return trajectory


#--------------------------------------
def _parse_traj_value(line, name, line_num, filename):
    try:
        return float(line[name])
    except ValueError:
        raise ValueError('Invalid value in line {:} in {:}: column {:} should be a number but it''s "{:}"'.format(line_num, filename, name, line[name]))


#----------------------------------------------------------------------------------------------
class TrajectoryPoint(object):
    """
    A single point recorded from the pen
    """

    def __init__(self, x, y, z, t):
        self.x = x
        self.y = y
        self.z = z
        self.t = t
