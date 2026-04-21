from pydub import AudioSegment

def convert_m4p_to_mp3(input_file, output_file):
    audio = AudioSegment.from_file(input_file, format="m4a")
    audio.export(output_file, format="mp3")
    print(f"Converted {input_file} to {output_file}")

input_file = "04 Rhiannon.m4p"
output_file = "04 Rhiannon.mp3"
convert_m4p_to_mp3(input_file, output_file)
