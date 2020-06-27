"""
Markup data for stimuli
"""
from operator import attrgetter


#--------------------------------------------------------------------------------------------------------------------
class Experiment(object):
    """
    All trials of one experiment session
    """

    #-----------------------------------------------------------------
    def __init__(self, trials=(), subj_id=None, source_path=None):
        self._trials = list(trials)
        self.subj_id = subj_id
        self.source_path = source_path


    #-----------------------------------------------------------------
    @property
    def trials(self):
        return tuple(self._trials)


    #-----------------------------------------------------------------
    @property
    def sorted_trials(self):
        return tuple(sorted(self._trials, key=attrgetter('trial_num')))


    #-----------------------------------------------------------------
    def append(self, trial):
        self._trials.append(trial)


    #-----------------------------------------------------------------
    def sort_trials(self):
        self._trials.sort(key=attrgetter('trial_num'))


    #-----------------------------------------------------------------
    @property
    def n_traj_points(self):
        return sum([trial.n_traj_points for trial in self._trials])



#--------------------------------------------------------------------------------------------------------------------
class RawTrial(object):
    """
    Information about one trial in the experiment, not yet coded (just a series of points)
    """

    #-----------------------------------------------------------------
    def __init__(self, trial_id, target_id, stimulus, traj_points, time_in_session=None, rc=None, source=None, self_correction = None,
                 sound_file_length = None,raw_file_name = None, time_in_day = None, date = None):
        self.target_id = target_id
        self.trial_id = trial_id
        self.stimulus = stimulus
        self.traj_points = traj_points
        self.time_in_session = time_in_session
        self.rc = rc
        self.source = source
        self.response = ''
        self.self_correction = self_correction
        self.sound_file_length = sound_file_length
        self.raw_file_name = raw_file_name
        self.time_in_day = time_in_day
        self.date = date

    #-----------------------------------------------------------------
    @property
    def on_paper_points(self):
        return [pt for pt in self.traj_points if pt.z > 0]


    #-----------------------------------------------------------------
    @property
    def n_traj_points(self):
        """
        The total number of points recorded in the trial
        """
        return len(self.traj_points)


#--------------------------------------------------------------------------------------------------------------------
class CodedTrial(object):
    """
    Information about one trial in the experiment, after coding.

    The trial contains a series of characters
    """

    #-----------------------------------------------------------------
    def __init__(self, trial_num, target_id, stimulus, response, characters, strokes, sub_trial_num=1, time_in_session=None, rc=None,self_correction = None, sound_file_length = None):
        self.trial_num = trial_num
        self.sub_trial_num = sub_trial_num
        self.target_id = target_id
        self.stimulus = stimulus
        self.response = response
        self.characters = characters
        self.strokes = strokes
        self.time_in_session = time_in_session
        self.rc = rc
        self.self_correction = self_correction
        self.sound_file_length = sound_file_length

    #-----------------------------------------------------------------
    @property
    def traj_points(self):
        return [pt for stroke in self.strokes for pt in stroke.trajectory]


    #-----------------------------------------------------------------
    @property
    def on_paper_points(self):
        return [pt for stroke in self.strokes if stroke.on_paper for pt in stroke.trajectory]


    #-----------------------------------------------------------------
    @property
    def n_traj_points(self):
        """
        The total number of points recorded in the trial
        """
        return sum([s.n_traj_points for s in self.strokes])


#--------------------------------------------------------------------------------------------------------------------
class Character(object):
    """
    A character, including the above-paper movement before/after it
    """

    def __init__(self, char_num, strokes=(), pre_char_space=None, post_char_space=None, character=None):
        """

        :param num: Serial number
        :param strokes: a list of the strokes (on/above paper) comprising the character
        :param pre_char_space: The above-paper stroke before the character
        :param post_char_space: The above-paper stroke after the character
        """
        self.char_num = char_num
        self.strokes = list(strokes)
        self.pre_char_space = pre_char_space
        self.post_char_space = post_char_space
        self.character = character


    @property
    def duration(self):
        """
        The duration it took to write the character (excluding the pre/post-character delay)
        """
        t_0 = self.strokes[0].trajectory[0].t
        t_n = self.strokes[-1].trajectory[-1].t
        return t_n - t_0

    @property
    def pre_char_delay(self):
        return 0 if self.pre_char_space is None else self.pre_char_space.duration


    @property
    def post_char_delay(self):
        return 0 if self.post_char_space is None else self.post_char_space.duration



#--------------------------------------------------------------------------------------------------------------------
class Stroke(object):
    """
    A consecutive trajectory part in which the pen is touching the paper, or the movement (above paper) between two such
    adjacent strokes.
    """

    def __init__(self, on_paper, char_num, trajectory):
        self.on_paper = on_paper
        self.char_num = char_num
        self.trajectory = trajectory
        self.correction = 0



    @property
    def n_traj_points(self):
        return len(self.trajectory)


    @property
    def duration(self):
        """
        The duration (in ms) it took to complete this stroke
        """
        t_0 = self.trajectory[0].t
        t_n = self.trajectory[-1].t
        return t_n - t_0


    def __iter__(self):
        return self.trajectory.__iter__()


#--------------------------------------------------------------------------------------------------------------------
class TrajectoryPoint(object):
    """
    A single point recorded from the pen
    """

    def __init__(self, x, y, z, t):
        self.x = x
        self.y = y
        self.z = z
        self.t = t
