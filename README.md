# Discord Video Encoder
Have you ever tried to upload a video to Discord, only for it to not fit in the 25MB file size cap? This is a convenient Python wrapper around FFmpeg that will use the two-pass average bitrate mode of `libx264` to smash whatever video you want into 25MB (or larger, if you're a Nitro user).

This is of course also useful for any other service which limits the upload size of videos.

Some other sensible modifications to the video and audio are made.

## Features

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
	- File size is capped by default at 10MB (may be a little off), with a max bit rate of 10Mbit/s
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

## Example usage

Prepare a file named `meme.mp4` into something ready to be uploaded to a Discord server.

```
discord-encode meme.mp4
```

You should now have a file called `meme_discord.mp4` in your current directory.

Now you want to upload to a boosted server with a 100MB upload limit, cut off the first 10 seconds, and make the result 5 seconds long. Save the output to `big_meme.mp4`.

```
discord-encode meme.mp4 -size 100 -ss 10 -t 5 -o big_meme.mp4
```

## Dependencies

 * Recent Python 3.x
 * FFmpeg

## Installation

On macOS and Linux, you can simply symlink the script to a location in your `$PATH`.

```
# ln -s $PWD/discord-encode.py /usr/local/bin/discord-encode
```

Otherwise invoke the Python executable and provide the script.

```
$ python3 discord-encode.py meme.mp4
```
