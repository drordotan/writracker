import numpy as np
import matplotlib.pyplot as plt
from moviepy.editor import VideoClip
from moviepy.video.io.bindings import mplfig_to_npimage
from collections import namedtuple
import csv
import logging


Point = namedtuple('Point', ['x', 'y', 'z', 't'])
MovieSegment = namedtuple('MovieSegment', ['kind', 'ds_num', 'data', 'n_frames', 'frame1'])


# noinspection PyAttributeOutsideInit
class MoviePlotter(object):

    #--------------------------------------------------------------------------
    def __init__(self, data, out_fn, titles=None, title_fontsize=8, speedup_factor=1.0,
                 end_of_dataset_delay=0.5, inter_dataset_delay=0.2, fps=20,
                 scale=1, plot_area_max_size=(5, 4), inner_margin=15, h_margin=0.1, v_margin=0.1,
                 point_size=5, black_pressure=128, invert=False):
        """
        Initialize MoviePlotter.

        Below,
        Plot area = area in which the trajectories are plotted
        Canvas = the entire figure, including the plot area and title
        Pixels = Measurement units, corresponding with the scaled trajectory x,y values

        :param data: Array of datasets, where each entry is a list of Point namedtuples OR a CSV filepath
        :param out_fn: Output movie filename
        :param titles: An optional list of strings - one title per dataset (displayed above the plot area)
        :param speedup_factor: Multiply typing speed by this factor
        :param end_of_dataset_delay: For how long (seconds) to hold the last frame of each dataset
        :param inter_dataset_delay: Duration (seconds) of blank screen between datasets
        :param fps: Output movie's frames per second
        :param scale: Scaling factor for translating x,y coordinates to pixels (1 = same).
                      This affects the ratio between plot area and point size - usually you'll have to change only one of them
        :param plot_area_max_size: The maximal size of the plot area (the dots) in inches: (width, height)
        :param inner_margin: Margin between the plot area boundaries and the plotted dots (specified in PIXELS)
        :param h_margin: Horizontal margin between the plot area and the canvas edges (specified in INCHES)
        :param v_margin: Vertical margin between the plot area and the canvas edges (specified in INCHES)
        :param point_size: Size of each dot
        :param black_pressure: Pressure value from 0-255 mapping to black threshold
        :param invert: Invert colors (black background, grey-to-white dots)
        """
        self.filename = out_fn
        self.titles = titles
        self.title_fontsize = title_fontsize
        self.speedup_factor = speedup_factor
        self.end_of_dataset_delay = end_of_dataset_delay
        self.inter_dataset_delay = inter_dataset_delay
        self.fps = fps
        self.scale = scale
        self.plot_area_max_size = plot_area_max_size
        self.inner_margin = inner_margin
        self.h_margin = h_margin
        self.v_margin = v_margin
        self.point_size = point_size
        self.black_pressure = black_pressure
        self.invert = invert

        self.datasets = self._load_data(data)
        self._align_and_rescale_dataset_points()
        self.progress_last = -1
        self.plt_segments = []

    #--------------------------------------------------------------------------
    def _load_data(self, data):
        """
        Load datasets if they were specified as file names
        """
        if not isinstance(data, list):
            raise ValueError('Data must be an array of datasets (each a list of Points or CSV file path).')

        datasets = []
        for d in data:
            if isinstance(d, str):
                datasets.append(self._load_points_from_csv(d))
            elif isinstance(d, list):
                if len(d) == 0:
                    raise ValueError('Each dataset must contain at least one Point.')
                datasets.append(d)
            else:
                raise ValueError('Each dataset must be a list of Points or a CSV file path.')

        if len(datasets) == 0:
            raise ValueError('No datasets provided.')

        return datasets

    #--------------------------------------------------------------------------
    def _load_points_from_csv(self, csv_path):
        points = []
        with open(csv_path, newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            if sum(fld not in reader.fieldnames for fld in ['x', 'y', 'pressure', 'time']) > 0:
                raise ValueError("CSV file must contain 'x', 'y', 'pressure', and 'time' columns.")
            for row in reader:
                if 'on_paper' in row and int(row['on_paper']) == 0:
                    continue
                if 'char_num' in row and int(row['char_num']) == 0:
                    continue
                x = float(row['x'])
                y = float(row['y'])
                z = float(row['pressure'])
                t = float(row['time'])
                if (x, y, z, t) != (0, 0, 0, 0):
                    points.append(Point(x, y, z, t))

        if len(points) == 0:
            raise ValueError("No valid points loaded from CSV.")

        return points

    #--------------------------------------------------------------------------
    def _align_and_rescale_dataset_points(self):
        w, h = self._dataset_dimensions()
        self.plot_area_size_pixels = max(w) * self.scale + self.inner_margin * 2, max(h) * self.scale + self.inner_margin * 2
        self._rescale_datasets(w, h)

    #--------------------------------------------------------------------------
    def _dataset_dimensions(self):

        def ds_width(dataset):
            x_vals = np.array([p.x for p in dataset]) * self.scale
            return np.max(x_vals) - np.min(x_vals)

        def ds_height(dataset):
            y_vals = np.array([p.y for p in dataset]) * self.scale
            return np.max(y_vals) - np.min(y_vals)

        widths = [ds_width(ds) for ds in self.datasets]
        heights = [ds_height(ds) for ds in self.datasets]

        return widths, heights

    #--------------------------------------------------------------------------
    def _rescale_datasets(self, ds_widths, ds_heights):
        """
        Rescale datasets to fit within the global plot dimensions.
        Each dataset is shifted to start at (0, 0) based on its own min coordinates.
        """

        def single_ds_scale_factor(w, h):
            factor_w = self.plot_area_size_pixels[0] / w if w > 0 else 1.0
            factor_h = self.plot_area_size_pixels[1] / h if h > 0 else 1.0
            return min(factor_w, factor_h)

        for i, (dataset, ds_w, ds_h) in enumerate(zip(self.datasets, ds_widths, ds_heights)):

            #-- Remove erroneous times and unprinted points
            dataset = [pt for pt in dataset if pt.t >= 0 and pt.z > 0]

            #-- Extract coordinates
            raw_x = np.array([p.x for p in dataset])
            raw_y = np.array([p.y for p in dataset])

            #-- Scale the dataset points
            ds_factor = single_ds_scale_factor(ds_w * self.scale, ds_h * self.scale)
            x_vals = raw_x * ds_factor
            y_vals = raw_y * ds_factor

            #-- Shift the dataset points to be centered at 0,0
            current_center_x = (max(x_vals) + min(x_vals)) / 2
            current_center_y = (max(y_vals) + min(y_vals)) / 2
            x_vals -= current_center_x
            y_vals -= current_center_y

            min_t = min(p.t for p in dataset)
            self.datasets[i] = [Point(x=x, y=y, z=p.z, t=p.t-min_t) for x, y, p in zip(x_vals, y_vals, dataset)]

    #--------------------------------------------------------------------------
    def plot(self):
        self.plt_total_duration = self._init_data_to_plot()
        self.init_progress_bar()

        self._setup_figure()
        self.plt_last_frame_num = None
        self.last_ind_in_segment = None
        animation = VideoClip(self._generate_frame, duration=self.plt_total_duration)
        animation.write_videofile(self.filename, fps=self.fps, logger=None)
        self.update_progress_bar(100)
        plt.close(self.plt_fig)
        self.plt_fig = None

    #--------------------------------------------------------------------------
    def _init_data_to_plot(self):
        """
        Create the actual data that will be plotted: consider each frame
        """
        self.plt_segments = []
        curr_frame = 0  # First frame is #0
        total_duration = 0

        n_ds = len(self.datasets)
        for i, dataset in enumerate(self.datasets):

            #-- Show the movie
            traj_points = self._dataset_to_segment(dataset)
            self.plt_segments.append(MovieSegment('draw', i, traj_points, len(traj_points), curr_frame))
            curr_frame += len(traj_points)
            total_duration += _ds_duration(dataset)

            #-- Hold the last frame
            if self.end_of_dataset_delay > 0:
                n_frames = self.sec_to_nframes(self.end_of_dataset_delay / self.speedup_factor)
                self.plt_segments.append(MovieSegment('hold', i, traj_points[-1], n_frames, curr_frame))
                curr_frame += n_frames
                total_duration += self.end_of_dataset_delay

            #-- Inter-dataset blank screen
            if i < n_ds - 1 and self.inter_dataset_delay > 0:
                n_frames = self.sec_to_nframes(self.inter_dataset_delay / self.speedup_factor)
                self.plt_segments.append(MovieSegment('blank', i, None, n_frames, curr_frame))
                curr_frame += n_frames
                total_duration += self.inter_dataset_delay

        return total_duration / self.speedup_factor

    #--------------------------------------------------------------------------
    @property
    def plt_total_n_frames(self):
        last_segment = self.plt_segments[-1]
        return last_segment.frame1 + last_segment.n_frames - 1

    #--------------------------------------------------------------------------
    def _dataset_to_segment(self, dataset):

        ds_duration = _ds_duration(dataset)
        ds_frame_duration = 1 / self.fps * self.speedup_factor

        times = np.arange(0, ds_duration, ds_frame_duration)

        raw_points = dataset
        raw_times = [p.t for p in raw_points]

        points = []

        for t in times:
            #-- Find the first point whose time is after 't'
            ind = np.searchsorted(raw_times, t, side='right')
            if ind >= len(raw_times):
                ind = len(raw_times) - 1

            points.append(raw_points[:ind])

            # Keep only points starting from the current one
            raw_points = raw_points[ind:]
            raw_times = raw_times[ind:]

        return points

    #--------------------------------------------------------------------------
    def init_progress_bar(self):
        self.progress_last = -1
        print('\n')
        self.update_progress_bar(0)

    #--------------------------------------------------------------------------
    def update_progress_bar(self, progress):
        progress = round(progress)
        bar_length = 50
        curr_progress = round(bar_length * progress / 100)
        if progress != self.progress_last:
            self.progress_last = progress
            bar = '#' * curr_progress + '-' * (bar_length - curr_progress)
            print(f"\r[{bar}] {round(progress)}%", end='', flush=True)

    #--------------------------------------------------------------------------
    def _compute_canvas_size(self):

        pixels_to_inch_ratio_x = self.plot_area_max_size[0] / self.plot_area_size_pixels[0]
        pixels_to_inch_ratio_y = self.plot_area_max_size[1] / self.plot_area_size_pixels[1]
        pixels_to_inch_ratio = min(pixels_to_inch_ratio_x, pixels_to_inch_ratio_y)

        plot_area_w = self.plot_area_size_pixels[0] * pixels_to_inch_ratio
        plot_area_h = self.plot_area_size_pixels[1] * pixels_to_inch_ratio

        font_height_inches = self.title_fontsize / 72.0
        canvas_width = plot_area_w + self.h_margin * 2
        canvas_height = plot_area_h + font_height_inches + self.v_margin * 2

        plot_area_rect = (self.h_margin / canvas_width, self.v_margin / canvas_height,
                          plot_area_w / canvas_width, plot_area_h / canvas_height)

        return (canvas_width, canvas_height), plot_area_rect

    #--------------------------------------------------------------------------
    def _setup_figure(self):

        canvas_size, plot_area_rect_as_pcnt = self._compute_canvas_size()

        bg_color = 'black' if self.invert else 'white'
        text_color = 'white' if self.invert else 'black'

        self.plt_fig = plt.figure(figsize=canvas_size, dpi=72, facecolor=bg_color)
        self.plt_fig.patch.set_facecolor(bg_color)

        ax = self.plt_fig.add_axes(plot_area_rect_as_pcnt, frameon=False)

        ax.set_facecolor(bg_color)

        width, height = self.plot_area_size_pixels
        ax.set_xlim([-width/2, width/2])
        ax.set_ylim([-height/2, height/2])

        #-- Hide axes and spines
        ax.axis('off')
        [spine.set_visible(False) for spine in ax.spines.values()]

        #-- Create the plotting handle
        cmap = 'gray' if self.invert else 'gray_r'
        self.plt_scatter = ax.scatter([], [], c=[], s=self.point_size, cmap=cmap, vmin=0, vmax=255)

        #-- Place the title just above the plot area
        self.plt_title = ax.text(
                x=0,  # center
                y=height/2 + self.h_margin,
                s='',
                ha='center', va='bottom',
                fontsize=self.title_fontsize,
                fontweight='bold',
                color=text_color,
                visible=False
        )

        self.plt_fig.tight_layout(rect=(0, 0, 1, 1))
        self.plt_xy = []
        self.plt_z = []

    #--------------------------------------------------------------------------
    def _find_segment_for_frame(self, frame_num):
        """
        Find the MovieSegment corresponding to the given frame number.
        """
        for segment in self.plt_segments:
            if segment.frame1 <= frame_num < segment.frame1 + segment.n_frames:
                return segment

        raise ValueError(f'Frame #{frame_num} is out of range.')

    #--------------------------------------------------------------------------
    def _generate_frame(self, t):

        frame_num = round(t * self.fps)

        seg = self._find_segment_for_frame(frame_num)

        if seg.kind == 'draw':
            self._plot_point(seg, frame_num)

        elif seg.kind == 'hold':
            pass

        elif seg.kind == 'blank':
            self._set_blank_frame()

        else:
            raise ValueError(f'Unknown segment kind: {seg.kind}')

        npimage = mplfig_to_npimage(plt.gcf())

        self.update_progress_bar(frame_num / self.plt_total_n_frames * 100)
        return npimage

    #--------------------------------------------------------------------------
    def _start_plotting_new_dataset(self, ds_ind):
        # if ds_ind == 1:
        #     [print(int(x), int(y)) for (x, y), z in zip(self.plt_xy, self.plt_z)]  # Debugging output for first dataset

        self.plt_xy = []
        self.plt_z = []
        self.plt_title.set_text(self.titles[ds_ind])
        self.plt_title.set_visible(True)
        self.last_ind_in_segment = None

    #--------------------------------------------------------------------------
    def _plot_point(self, segment, frame_num):

        ind_in_segment = frame_num - segment.frame1
        if ind_in_segment < 0:
            ind_in_segment = 0
        elif ind_in_segment >= segment.n_frames:
            ind_in_segment = segment.n_frames - 1

        if ind_in_segment == self.last_ind_in_segment:
            #-- No new point to add
            return

        self.last_ind_in_segment = ind_in_segment

        if ind_in_segment == 0:
            self._start_plotting_new_dataset(segment.ds_num)

        #print(f'Add point for frame #{frame_num}')
        self._add_points(segment.data[ind_in_segment])

        self.plt_scatter.set_offsets(self.plt_xy)
        self.plt_scatter.set_array(self.plt_z)

    #--------------------------------------------------------------------------
    def _add_points(self, points):
        for point in points:
            ##print(f'Adding point at ({point.x}, {point.y}: {point.z}')
            self.plt_xy.append((point.x, point.y))
            normalized_z = round(min(point.z, self.black_pressure) / self.black_pressure * 255)
            self.plt_z.append(normalized_z)

    #--------------------------------------------------------------------------
    def _set_blank_frame(self):
        self.plt_scatter.set_offsets(np.empty((0, 2)))
        self.plt_scatter.set_array([])
        self.plt_title.set_visible(False)

    #---------------------------------------------------------------------------
    def sec_to_nframes(self, sec):
        """ Convert seconds to number of frames based on the current fps """
        return int(np.ceil(sec * self.fps))


#--------------------------------------------------------------------------
def _ds_duration(dataset):
    times = np.array([p.t for p in dataset])
    return np.max(times) - np.min(times)


#--------------------------------------------------------------------------
def _silent_logger(*args, **kwargs):
    pass


#--------------------------------------------------------------------------
class SilentLogger(logging.Logger):

    def __init__(self):
        super().__init__('SilentLogger', level=logging.CRITICAL)

    def handle(self, record):
        pass

    def addHandler(self, hdlr):
        pass

    def debug(self, msg, *args, **kwargs):
        pass

    def info(self, msg, *args, **kwargs):
        pass

    def warning(self, msg, *args, **kwargs):
        pass

    def error(self, msg, *args, **kwargs):
        pass

    def critical(self, msg, *args, **kwargs):
        pass
