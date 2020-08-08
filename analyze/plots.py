import math

from matplotlib.backends.backend_pdf import PdfPages

import numpy as np
import matplotlib.pyplot as plt
from matplotlib import patches

from analyze.transform import get_bounding_box
import utils as u


#------------------------------------------------------------------------------
class TrialDecorationConfig(object):
    def __init__(self, bounding_box=False, temporal_gaps=False, fraction_of_x_points=None, fraction_of_y_points=None):
        self.bounding_box = bounding_box
        self.temporal_gaps = temporal_gaps
        self.fraction_of_x_points = fraction_of_x_points
        self.fraction_of_y_points = fraction_of_y_points


#------------------------------------------------------------------------------
def plot_trial(trial, n_colors=10, get_z_levels=None, ax=None, decorations=None):
    """
    Plot the trial raw data - the characters, as the subject wrote them.

    :type trial: Trial
    :param n_colors: No. of colors to use to denote level of pressure
    :param ax: The axes to use for plotting
    """
    if isinstance(trial, data.RawTrial):
        draw_extras = False

    lightest_color = 0.95

    points = trial.on_paper_points
    if len(points) == 0:
        return

    x = np.array([point.x for point in points])
    y = np.array([point.y for point in points])
    z = np.array([point.z for point in points])
    # minz = int(min(z))
    if get_z_levels is None:
        z = _convert_z_to_level(z, max(z), n_colors)
    else:
        z = get_z_levels(z)

    if ax is None:
        ax = plt.figure()

    if decorations is not None:
        _draw_trial_rectangles(trial, ax, decorations)

    for z_level in range(n_colors+1):
        inds = z == z_level
        if sum(inds) > 0:
            color = lightest_color * (1 - z_level/n_colors)
            #before:
            color = (color, ) * 3

            #c = int(minz/10)
            #mult = c if (c>3 and c< 5) else 3
            #color = (color, ) * (int(mult))
            ax.scatter(x[inds], y[inds], color=color, s=4)

    if decorations is not None:
        _draw_trial_rectangles(trial, ax, decorations)


#------------------------------------------------------------------------------
def plot_trials(exp, out_fn, cols_per_page=2, rows_per_page=5, n_colors=10, max_trials=None, decorations=None):
    """
    Plot the experiment raw data - the characters, as the subject wrote them - and save to a PDF file.

    :param exp: Experiment object
    :param out_fn: PDF file name
    :param cols_per_page: No. of trial columns in each page
    :param rows_per_page: No. of trial rows in each page
    :param n_colors: No. of colors to use to denote level of pressure
    :param max_trials: Plot only the first trials in the experiment
    """

    n_trials_per_page = cols_per_page * rows_per_page

    pdf = PdfPages(out_fn)
    trials = list(exp.sorted_trials)
    z_values = np.array([point.z for t in trials for point in t.on_paper_points])
    max_z = max(z_values)
    def get_z_levels(z):
        return _convert_z_to_level(z, max_z, n_colors)

    if max_trials is not None:
        trials = trials[:min(max_trials, len(trials))]

    n_pages = math.ceil(len(trials) / n_trials_per_page)

    progress = u.ProgressBar(len(trials), 'Preparing pdf...')
    n_done = 0

    while len(trials) > 0:

        curr_page_n_trials = min(n_trials_per_page, len(trials))
        fig, axes = plt.subplots(rows_per_page, cols_per_page)
        fig.subplots_adjust(hspace=.8, wspace=0.3)

        axes = np.reshape(axes, [n_trials_per_page])

        for i in range(curr_page_n_trials):
            trial = trials.pop(0)
            n_done += 1
            ax = axes[i]
            ax.get_yaxis().set_visible(False)
            ax.get_xaxis().set_visible(False)
            ax.set_title(_trial_title(trial), fontdict=dict(fontsize=5))
            plot_trial(trial, ax=ax, get_z_levels=get_z_levels, decorations=decorations)

        if curr_page_n_trials < n_trials_per_page:
            for i in range(curr_page_n_trials, n_trials_per_page):
                ax = axes[i]
                ax.get_yaxis().set_visible(False)
                ax.get_xaxis().set_visible(False)

        pdf.savefig(fig)
        plt.close(fig)

        progress.progress(n_done)

    pdf.close()

    if n_pages > 3:
        print('')


#-------------------------------------------------------------
def _convert_z_to_level(z_values, max_z, n_colors):
    return np.round(z_values * (n_colors / max_z)).astype(int)


#-------------------------------------------------------------
def _trial_title(trial):

    title = 'Trial {:}'.format(trial.trial_id)

    if trial.target_id is not None:
        title += '(#{:})'.format(trial.target_id)

    if trial.stimulus is not None:
        if trial.stimulus.isnumeric:
            title += ': {:,d}'.format(trial.stimulus)
        else:
            title += ': {:}'.format(trial.stimulus)

    return title


#-------------------------------------------------------------
def _draw_trial_rectangles(trial, ax, config=None):

    config = config or TrialDecorationConfig()
    if not config.bounding_box and not config.temporal_gaps:
        return

    characters = trial.characters

    gaps = []
    ys = []
    xs = []
    firstx = 0

    for n, c in enumerate(characters):
        box = get_bounding_box(c, fraction_of_x_points=config.fraction_of_x_points, fraction_of_y_points=config.fraction_of_y_points)
        x, y = box[4], box[5]
        ys.append(int(y))
        xs.append(int(x))
        if characters.index(c)==0:
            firstx = x

        gap = " " * int(c.pre_char_delay/120)
        gap += "\npre-"+ str(c.character) + ":\n"
        gap += (" {0:.2f}s".format(c.pre_char_delay))

        gaps.append(gap)

        if config.bounding_box:
            rect = patches.Rectangle((x, y), box[1], box[3],
                                     edgecolor='r' if (n % 2 == 0) else 'b', facecolor='none')
            rect.set_linewidth(0.01)
            ax.add_patch(rect)


    #-- Plot temporal gaps
    if config.temporal_gaps:
        bott = int(min(ys))
        for i in range(len(gaps)):
            #print("bott-100 is " + str(bott-100))
            ax.text(firstx-100 +i*510, bott-150, gaps[i], fontsize=4, ha="left", va="center",
                bbox=dict(boxstyle="square",linewidth=0.3, ec=(1., 0.5, 0.5), fc=(1., 0.8, 0.8) if i%2==0 else (1., 0.65, 0.65)))
