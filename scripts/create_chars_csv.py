"""
Re-create the character.csv files of the given sessions
"""
import os
import glob
import writracker.encoder


dirnames = glob.glob('/Users/dror/data/acad-proj/2-InProgress/hierarchical syntax/data/raw/coded/*/*')

for dir_name in dirnames:
    if not os.path.isdir(dir_name) or not os.path.isfile(f'{dir_name}/trials.csv'):
        continue

    print(f'Processing {dir_name}...')

    writracker.encoder.dataio.save_characters_file(dir_name)
