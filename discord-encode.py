#!/usr/bin/env python3

import os
import sys
import subprocess
import json
from pathlib import Path

original_args = {}
files = []

def arrify_dict(d):
	arr = []
	for key in d:
		if isinstance(d[key], list):
			for item in d[key]:
				arr.append(key)
				arr.append(str(item))
			continue
		
		arr.append(key)
		
		if d[key] != None:
			arr.append(str(d[key]))
	
	return arr



def parse_time(t):
	time_parts = [float(x) for x in t.split(":")]
	
	# Seconds
	time = time_parts[-1]
	
	# Minutes
	if len(time_parts) > 1:
		time += 60 * time_parts[-2]
	
	# Hours
	if len(time_parts) > 2:
		time += 60*60 * time_parts[-3]
	
	# Days
	if len(time_parts) > 3:
		time += 24*60*60 * time_parts[-4]
	
	return time



arg_key = None
for arg in sys.argv[1:]:
	if arg_key != None:
		if arg[0] == '-':
			original_args[arg_key] = None
			arg_key = None
		else:
			if arg_key in original_args:
				if not isinstance(original_args[arg_key], list):
					original_args[arg_key] = [original_args[arg_key]]
				original_args[arg_key].append(arg)
			else:
				original_args[arg_key] = arg
			arg_key = None
			continue
	
	if arg[0] == '-':
		arg_key = arg
		continue
	
	# Filenames are all non-hypen arguments
	files.append(arg)

if arg_key != None:
	original_args[arg_key] = None

if len(files) == 0:
	print("Missing filename", file = sys.stderr)

if "-h" in original_args or len(files) == 0:
	print("""Discord video encoder
	* Can take multiple files and process them in sequence
		- All arguments that don't start with `-` are interpreted as input files
	* Re-encodes audio with AAC when
		- Current audio is a different codec
		- Current audio bitrate is > 200kb/s
		- `-ss` start time option is supplied (this seems to cause sync issues on the macOS Discord client if the audio is not re-encoded)
		- Audio takes up more than 15% of the total file size
	* Resizes video when
		- Video is larger than 1080p, resize to 1080p
		- Video is longer than 2 minutes, resize to 720p
		- Pass `-keep-size` to disable resizing
	* If average FPS is > 60, limit to 60
		- Pass `-keep-fps` to disable this
	* Uses two-pass ABR to target a known file size
		- File size is capped by default at 24MB (may be a little off), with a max bit rate of 10Mbit/s
		- Pass `-size [size in MB]` to override default size; e.g. `-size 100` to get a 100MB file
	* Metadata is stripped so you don't accidentally doxx yourself (though Discord does strip most metadata itself)
	* Use `-o [path]` to define an output path
		- If not specified, the original filename is used with `_discord` appended
		- Ensure it ends with `.mp4` for optimal compatibility
		- Used as output file suffix when processing multiple files
	* All other arguments are passed through to FFmpeg
		- Provided arguments override the default ones from this script
		- `-ss` and `-t` options are useful for trimming video
		- `-an` option to remove audio
	""", file = sys.stderr)
	exit(1)



# Determine the best available AAC encoder
aac_encoder = "aac"
encoder_list_proc = subprocess.Popen(["ffmpeg", "-hide_banner", "-encoders"], stdout = subprocess.PIPE)
encoder_list = str(encoder_list_proc.stdout.read())
if " aac_at " in encoder_list:
	aac_encoder = "aac_at"
elif " libfdk_aac " in encoder_list:
	aac_encoder = "libfdk_aac"



# Determine what null file to use
devnull = "/dev/null"
if os.name == "nt":
	devnull = "NUL"



for ind in range(len(files)):
	filename = files[ind]
	args = dict(original_args)
	
	# Get video info with ffprobe
	probe = subprocess.Popen(["ffprobe", "-v", "warning", "-print_format", "json", "-show_format", "-show_streams", filename], stdout = subprocess.PIPE)
	
	probe_return_code = probe.wait()
	if probe_return_code != 0:
		exit(probe_return_code)
	
	info = json.loads(probe.stdout.read())
	
	
	
	# Get duration
	duration = float(info["format"]["duration"])
	
	if "-ss" in args:
		duration -= parse_time(args["-ss"])
	
	if "-t" in args:
		duration = min(duration, parse_time(args["-t"]))
	
	
	
	# Determine target file size in kbits
	target_size = 24000*8
	if "-size" in args:
		target_size = float(args["-size"]) * 8000
		del args["-size"]
	
	
	
	# Determine if we need to re-encode audio and at what bitrate
	reencode_audio = False
	audio_bitrate = 128
	has_audio = False
	
	# Check current audio stream
	for stream in info["streams"]:
		if stream["codec_type"] == "audio":
			has_audio = True
			
			if stream["codec_name"] == "aac":
				if "bit_rate" in stream:
					audio_bitrate_found = float(stream["bit_rate"])
					if audio_bitrate_found > 200e3:
						reencode_audio = True
					else:
						audio_bitrate = audio_bitrate_found/1000
				else:
					reencode_audio = True
			else:
				reencode_audio = True
			break
	
	if "-ss" in args:
		reencode_audio = True
	
	if "-an" in args:
		has_audio = False
	
	# Make sure we use less than 15% of the total file size for audio
	max_audio_bitrate = target_size * 0.15 / duration
	if audio_bitrate > max_audio_bitrate:
		audio_bitrate = round(max_audio_bitrate)
		reencode_audio = True
	
	try:
		if "-b:a" in args:
			ba = args["-b:a"]
			if ba[-1] == "k":
				ba = ba[:-1]
				audio_bitrate = float(ba)
			else:
				audio_bitrate = float(ba)/1000
			reencode_audio = True
	except:
		print("Cannot parse audio bitrate setting", file = sys.stderr)
	
	
	
	# Determine video bitrate
	
	# Subtract away audio size
	if has_audio:
		target_size -= audio_bitrate * duration
	
	if target_size < 0:
		print("Video needs to be negative size to fit. Oh no.")
		exit(1)
	
	video_bitrate = round(min(10000, target_size/duration))
	
	
	
	# Determine if we need to limit video resolution
	limit_resolution = False
	target_resolution = 1080
	
	if "-keep-size" in args:
		del args["-keep-size"]
	else:
		if duration > 120:
			limit_resolution = True
			target_resolution = 720
		
		for stream in info["streams"]:
			if stream["codec_type"] == "video":
				if float(stream["height"]) > 1080:
					limit_resolution = True
				break
	
	
	
	# Check for very high FPS
	limit_fps = False
	
	if "-keep-fps" in args:
		del args["-keep-fps"]
	else:
		for stream in info["streams"]:
			if stream["codec_type"] == "video":
				if int(stream["nb_frames"])/float(info["format"]["duration"]) > 61:
					limit_fps = True
				break
	
	
	
	# Determine output path
	path_obj = Path(filename)
	output_path = str(path_obj.parent / (path_obj.stem + "_discord.mp4"))
	
	if "-o" in args:
		output_path = args["-o"]
		del args["-o"]
		
		# Use -o option as suffix instead of actual path when outputting multiple files
		if len(files) > 1:
			output_path = str(path_obj.parent / (path_obj.stem + output_path))
	
	# Check if file exists
	if "-y" not in args and Path(output_path).exists():
		print(f"File {output_path} exists! Pass -y to overwrite", file = sys.stderr)
		exit(1)
	
	
	
	# Create arguments for first ffmpeg pass
	pass1_args = {
		"-hide_banner": None,
		"-ss": "0",
		"-i": filename,
		"-map_metadata": "-1",
		"-map": ["0:v:0"],
		"-c:v": "libx264",
		"-b:v": str(video_bitrate) + "k",
		"-preset": "slow",
		"-pass": "1",
		"-pix_fmt": "yuv420p",
		"-fps_mode": "cfr",
		"-y": None,
		"-f": "null"
	}
	
	if limit_resolution:
		pass1_args["-vf"] = "scale=-1:" + str(target_resolution)
	
	if limit_fps:
		pass1_args["-r"] = "60"
	
	# Disallow some arguments
	args.pop("-i", None)
	args.pop("-pass", None)
	custom_args_pass1 = dict(args)
	custom_args_pass1.pop("-b:a", None)
	custom_args_pass1.pop("-c:a", None)
	custom_args_pass1.pop("-an", None)
	custom_args_pass1.pop("-o", None)
	
	pass1_args.update(custom_args_pass1)
	
	# Run pass 1
	pass1 = ["ffmpeg"] + arrify_dict(pass1_args) + [devnull]
	print("Running pass 1: \"" + " ".join(pass1) + "\"")
	result = subprocess.run(pass1)
	
	if result.returncode != 0:
		exit(result.returncode)
	
	
	
	# Create arguments for second ffmpeg pass
	pass2_args = {
		"-hide_banner": None,
		"-ss": "0",
		"-i": filename,
		"-map_metadata": "-1",
		"-map": ["0:v:0"],
		"-c:v": "libx264",
		"-b:v": str(video_bitrate) + "k",
		"-preset": "slow",
		"-pass": "2",
		"-pix_fmt": "yuv420p",
	}
	
	if limit_resolution:
		pass2_args["-vf"] = "scale=-1:" + str(target_resolution)
	
	if limit_fps:
		pass1_args["-r"] = "60"
	
	if has_audio:
		pass2_args["-map"].append("0:a:0")
		
		if reencode_audio:
			pass2_args["-c:a"] = aac_encoder
			pass2_args["-b:a"] = str(audio_bitrate) + "k"
		else:
			pass2_args["-c:a"] = "copy"
	
	pass2_args.update(args)
	
	# Run pass 2
	pass2 = ["ffmpeg"] + arrify_dict(pass2_args) + [output_path]
	print("\n\n\nRunning pass 2: \"" + " ".join(pass2) + "\"")
	result = subprocess.run(pass2)
	
	if result.returncode != 0:
		exit(result.returncode)
	
	
	
	# Remove log files
	for f in Path(".").glob("ffmpeg2pass-0.log*"):
		f.unlink()
	
	
	
	if ind < len(files) - 1:
		print("\n\n\n")
