import numpy as np
import matplotlib.pyplot as plt
from moviepy.editor import VideoClip
from moviepy.video.io.bindings import mplfig_to_npimage
from collections import namedtuple
import csv

Point = namedtuple('Point', ['x', 'y', 'z', 't'])


class MoviePlotter(object):

    #--------------------------------------------------------------------------
    def __init__(self, data, out_fn, speedup_factor=1.0, fps=30, title=None, black_pressure=255, scale=1.0):
        """
        Initialize MoviePlotter.

        Parameters:
        - data: list of Point namedtuples OR CSV filepath
        - out_fn: output movie filename
        - speedup_factor: speed multiplier
        - fps: frames per second
        - title: optional string for title text displayed above rectangle
        - black_pressure: pressure value from 0-255 mapping to black threshold
        - scale: scale factor for x,y coordinates (>1 = enlarge)
        """
        self.filename = out_fn
        self.speedup_factor = speedup_factor
        self.fps = fps
        self.title = title
        self.black_pressure = black_pressure
        self.scale = scale

        self.points = self._load_data(data)
        self._prepare_arrays()
        self.progress_last = -1

    #--------------------------------------------------------------------------
    def _load_data(self, data):
        if isinstance(data, str):
            return self._load_points_from_csv(data)
        elif isinstance(data, list):
            return data
        else:
            raise ValueError("Data must be list of Points or CSV file path.")

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
    def _prepare_arrays(self):
        raw_x = np.array([p.x for p in self.points])
        raw_y = np.array([p.y for p in self.points])
        self.x_vals = raw_x * self.scale
        self.y_vals = raw_y * self.scale

        raw_z = np.array([p.z for p in self.points])
        clipped_z = np.clip(raw_z, 0, self.black_pressure)
        scaled_z = (clipped_z / self.black_pressure) * 255
        self.z_vals = scaled_z.astype(np.uint8)

        self.timestamps = np.array([p.t for p in self.points])
        self.adjusted_times = (self.timestamps - self.timestamps[0]) / self.speedup_factor
        self.total_duration = self.adjusted_times[-1]

        self.total_frames = int(np.ceil(self.total_duration * self.fps))

    #--------------------------------------------------------------------------
    def init_progress_bar(self):
        print("Rendering video:")
        print("[{}] 0%".format(' ' * 50), end='\r', flush=True)

    #--------------------------------------------------------------------------
    def update_progress_bar(self, current_frame):
        bar_length = 50
        progress = min(current_frame / self.total_frames, 1.0)
        block = int(round(bar_length * progress))
        if block != self.progress_last:
            self.progress_last = block
            bar = '#' * block + '-' * (bar_length - block)
            percent = int(progress * 100)
            print(f"[{bar}] {percent}%", end='\r', flush=True)

    #--------------------------------------------------------------------------
    def _setup_figure(self):
        fig, ax = plt.subplots()

        xmin, xmax = np.min(self.x_vals), np.max(self.x_vals)
        ymin, ymax = np.min(self.y_vals), np.max(self.y_vals)

        ax.set_xlim(xmin, xmax)
        ax.set_ylim(ymin, ymax)

        # Enforce equal aspect ratio so data aspect ratio is preserved exactly
        # 'datalim' makes limits fixed to data limits, without autoscale stretching
        ax.set_aspect('equal', adjustable='datalim')

        ax.axis('off')
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_frame_on(False)

        rect = plt.Rectangle((xmin, ymin), xmax - xmin, ymax - ymin,
                             linewidth=1.5, edgecolor='black', facecolor='none')
        ax.add_patch(rect)

        if self.title:
            # Position title just above the rectangle top center
            ax.text((xmin + xmax) / 2, ymax, self.title,
                    ha='center', va='bottom', fontsize=14, fontweight='bold')

        scatter = ax.scatter([], [], c=[], s=10, cmap='gray_r', vmin=0, vmax=255)
        return fig, ax, scatter

    #--------------------------------------------------------------------------
    def _make_frame(self, scatter):
        def frame_func(t):
            frame_num = int(t * self.fps)
            idx = np.searchsorted(self.adjusted_times, t, side='right') - 1
            idx = max(0, min(idx, len(self.points) - 1))
            current_x = self.x_vals[:idx+1]
            current_y = self.y_vals[:idx+1]
            current_z = self.z_vals[:idx+1]
            scatter.set_offsets(np.c_[current_x, current_y])
            scatter.set_array(current_z)
            self.update_progress_bar(frame_num)
            return mplfig_to_npimage(plt.gcf())
        return frame_func

    #--------------------------------------------------------------------------
    def plot(self):
        self.init_progress_bar()
        fig, ax, scatter = self._setup_figure()
        animation = VideoClip(self._make_frame(scatter), duration=self.total_duration)
        animation.write_videofile(self.filename, fps=self.fps)
        self.update_progress_bar(self.total_frames)
        plt.close(fig)
