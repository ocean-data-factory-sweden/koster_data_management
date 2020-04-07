#################################################
### THIS FILE WAS AUTOGENERATED! DO NOT EDIT! ###
#################################################
# file to edit: dev_nb/upload_clips.ipynb
# Import required packages
import os, math, csv
import subprocess
import argparse
import sqlite3
import numpy as np
from db_setup import *
from zooniverse_setup import *
from datetime import date
from panoptes_client import (
    SubjectSet,
    Subject,
    Project,
    Panoptes,
)  # needed to upload clips to Zooniverse


def get_length(filename):
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            filename,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return float(result.stdout)


def main():

    "Handles argument parsing and launches the correct function."
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--user", "-u", help="Zooniverse username", type=str, required=True
    )
    parser.add_argument(
        "--password", "-p", help="Zooniverse password", type=str, required=True
    )
    parser.add_argument(
        "--location", "-l", help="Location to store clips", type=str, required=True
    )
    parser.add_argument(
        "--video_path", "-v", help="Video to clip", type=str, required=True
    )
    parser.add_argument(
        "--n_clips", "-n", help="Number of clips to sample", type=str, required=True
    )
    parser.add_argument(
        "-db",
        "--db_path",
        type=str,
        help="the absolute path to the database file",
        default=r"koster_lab.db",
        required=True,
    )
    args = parser.parse_args()

    # Connect to koster_db
    conn = create_connection(args.db_path)

    video_filename = str(os.path.basename(args.video_path))
    video_duration = get_length(args.video_path)
    v_filename, ext = os.path.splitext(video_filename)

    # Add to movies table
    try:
        insert_many(conn, [(video_filename, None, None, None, None, None)], "movies", 6)
    except sqlite3.Error as e:
        print(e)

    # Specify how many clips to generate and its length (seconds)
    n_clips = args.n_clips
    clip_length = 10

    # Specify the folder location to store the clips
    location = args.location
    if not os.path.exists(location):
        os.mkdir(location)

    # Specify the project number of the koster lab
    koster_project = auth_session(args.user, args.password)

    # Query the koster lab database to randomly select n clips from movie sections that haven't been clipped yet
    try:
        min_time = exec_query(
            conn,
            f"SELECT min(start_time) FROM clips WHERE movie_filename == {video_filename}",
        )
    except:
        min_time = 0
    try:
        max_time = exec_query(
            conn,
            f"SELECT max(end_time) FROM clips WHERE movie_filename == {video_filename}",
        )
    except:
        max_time = 0

    if min_time > 0:
        before = [
            (a, b)
            for a, b in zip(
                range(0, min_time - clip_length, clip_length),
                range(clip_length, min_time, clip_length),
            )
        ]
    else:
        before = []

    after = [
        (a, b)
        for a, b in zip(
            range(max_time, video_duration - clip_length, clip_length),
            range(max_time + clip_length, video_duration, clip_length),
        )
    ]

    clip_list = before + after
    clip_list = [
        tuple(i)
        for i in np.array(clip_list)[
            np.random.choice(
                range(len(clip_list)), min(len(clip_list), n_clips), replace=False
            )
        ]
    ]

    # Create empty subject metadata to keep track of the clips generated
    subject_metadata = {}

    # Generate one clip at the time, update the koster lab database and the subject_metadata
    for clip in clip_list:
        # Generate and store the clip
        subject_filename = v_filename + "_" + str(int(clip[0])) + ".mp4"
        fileoutput = location + os.sep + subject_filename
        subprocess.call(
            [
                "ffmpeg",
                "-ss",
                str(clip[0]),
                "-t",
                str(clip_length),
                "-i",
                args.video_path,
                "-c",
                "copy",
                "-force_key_frames",
                "1",
                fileoutput,
            ]
        )

        # Add clip information to the koster lab database
        # clip_id =
        filename = subject_filename
        start_time = clip[0]
        end_time = clip[1]
        clip_date = date.today().strftime("%d_%m_%Y")

        # Add to clips to db
        try:
            insert_many(
                conn,
                [(filename, None, start_time, end_time, None, video_filename)],
                "clips",
                6,
            )
        except sqlite3.Error as e:
            print(e)

        # Add clip information to the subject_metadata
        subject_metadata[clip] = {
            "filename": subject_filename,
            "#start_time": start_time,
            "#end_time": end_time,
            "clip_date": clip_date,
        }

    print(len(clip_list), " clips have been generated in ", location, ".")

    # Create a new subject set (the Zooniverse dataset that will store the clips)
    set_name = input("clips_" + date.today().strftime("%d_%m_%Y"))
    previous_subjects = []

    try:
        # check if the subject set already exits
        subject_set = SubjectSet.where(
            project_id=koster_project.id, display_name=set_name
        ).next()
        print(
            "You have chosen to upload ",
            len(subject_metadata),
            " files to an existing subject set",
            set_name,
        )
        retry = input(
            'Enter "n" to cancel this upload, any other key to continue' + "\n"
        )
        if retry.lower() == "n":
            quit()
        for subject in subject_set.subjects:
            previous_subjects.append(subject.metadata["filename"])
    except StopIteration:
        print(
            "You have chosen to upload ",
            len(subject_metadata),
            " files to an new subject set ",
            set_name,
        )
        retry = input(
            'Enter "n" to cancel this upload, any other key to continue' + "\n"
        )
        if retry.lower() == "n":
            quit()
        # create a new subject set for the new data and link it to the project above
        subject_set = SubjectSet()
        subject_set.links.project = koster_project
        subject_set.display_name = set_name
        subject_set.save()

    # Upload the clips to the project
    print("Uploading subjects, this could take a while!")
    new_subjects = 0

    for filename, metadata in subject_metadata.items():
        try:
            if filename not in previous_subjects:
                subject = Subject()
                subject.links.project = koster_project
                subject.add_location(location + os.sep + filename)
                subject.metadata.update(metadata)
                subject.save()
                subject_set.add(subject.id)
                print(filename)
                new_subjects += 1
        except panoptes_client.panoptes.PanoptesAPIException:
            print("An error occurred during the upload of ", filename)
    print(new_subjects, "new subjects created and uploaded")

    # Generate a csv file with all the uploaded clips
    uploaded = 0
    with open(location + os.sep + "Uploaded subjects.csv", "wt") as file:
        subject_set = SubjectSet.where(
            project_id=koster_project.id, display_name=set_name
        ).next()
        for subject in subject_set.subjects:
            uploaded += 1
            file.write(subject.id + "," + list(subject.metadata.values())[0] + "\n")

            # Add to subjects db
            try:
                insert_many(
                    conn,
                    [
                        (
                            subject.id,
                            None,
                            subject_set.id,
                            None,
                            None,
                            None,
                            subject.metadata["clip_date"],
                            subject.metadata["filename"],
                        )
                    ],
                    "subjects",
                    8,
                )
            except:
                pass
        print(
            uploaded,
            " subjects found in the subject set, see the full list in Uploaded subjects.csv.",
        )
    conn.commit()


if __name__ == "__main__":
    main()
