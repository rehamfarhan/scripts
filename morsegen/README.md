# morsegen

Converts text to Morse code and back.

Useful for practice, for testing a decoder, or for producing Morse without opening a web page. The symbols are configurable, because not everything uses `.` and `-`; some keys, logbooks and study material use `·`, `_` or other marks.

## What it does

- `encode`: text to Morse.
- `decode`: Morse to text.
- `--dot`, `--dash`, `--sep`: use different symbols for dot, dash and the word separator.
- Rejects configurations where two of those symbols are the same, since the output would be ambiguous.

Both subcommands and short flags work. `morsegen encode "HI"` and `morsegen -e "HI"` are the same.

## Install

```bash
sudo ../scrlink/scrlink.sh morsegen/morsegen.py morsegen
# or
sudo scrlink morsegen
```

## Usage

```bash
morsegen encode "HELLO WORLD"
morsegen decode ".... . .-.. .-.. --- / .-- --- .-. .-.. -.."

# same thing with flags
morsegen -e "HELLO WORLD"
morsegen -d ".... . .-.. .-.. ---"

# custom symbols
morsegen encode "HELLO" --dot "." --dash "_" --sep "/"
```

Words are separated by `/` by default. Letters are separated by spaces.

## Requirements

Python 3. No external packages.
