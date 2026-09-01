#!/usr/bin/env python3
import sys
import random

# ANSI Color Codes
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

def get_key():
    """Detects a single keypress without requiring Enter."""
    if not sys.stdin.isatty():
        return sys.stdin.read(1)
    try:
        import tty, termios
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch
    except (ImportError, Exception):
        # Fallback for Windows or non-standard terminals
        try:
            import msvcrt
            return msvcrt.getch().decode('utf-8', errors='ignore')
        except ImportError:
            return sys.stdin.read(1)

def prompt_float(prompt_msg):
    while True:
        try:
            return float(input(prompt_msg))
        except ValueError:
            print(f"{RED}Invalid input. Please enter a valid number.{RESET}")

def roll_number(lower, upper, include_limits, is_decimal, decimals=2, lower_int=None, upper_int=None):
    """Generates a single formatted random number based on configuration."""
    if is_decimal:
        val = random.uniform(lower, upper)
        if not include_limits:
            while val == lower or val == upper:
                val = random.uniform(lower, upper)
        return f"{val:.{decimals}f}"
    else:
        if lower_int is None or upper_int is None:
            lower_int = int(lower)
            upper_int = int(upper)
            if not include_limits:
                lower_int += 1
                upper_int -= 1
        return str(random.randint(lower_int, upper_int))

def print_help():
    """Displays detailed CLI help with usage and examples."""
    help_text = f"""{BOLD}{CYAN}🎲 Random Number Generator (rng){RESET}

{BOLD}Usage:{RESET}
  rng                                                Interactive setup wizard
  rng <lower-limit> <upper-limit> [inclusion] [type] [decimals]

{BOLD}Arguments & Options:{RESET}
  <lower-limit>      Lower bound
  <upper-limit>      Upper bound
  [inclusion]        Inclusion mode (default: 1)
                     1 = Inclusive [min, max]
                     2 = Exclusive (min, max)
  [type]             Number type (default: 1)
                     1 = Whole numbers / Integers
                     2 = Decimal numbers / Floats
  [decimals]         Decimal precision (default: 2, when type=2)

{BOLD}Examples (bypasses wizard directly into the generator):{RESET}
  rng 1 4            # Rolls integers 1 to 4 on any keypress
  rng 1 10 2 1       # Exclusive integers 2 to 9 on any keypress
  rng 1 10 1 2       # Decimals with 2 places (e.g. 6.38)
  rng 1 10 1 2 4     # Decimals with 4 places (e.g. 8.9202)
"""
    print(help_text.strip())

def start_generator_loop(lower, upper, include_limits, is_decimal, decimals=2, lower_int=None, upper_int=None):
    """Runs the live generator loop that rolls a new number on each keypress."""
    print(f"\n{GREEN}✔ Configuration locked!{RESET}")
    print(f"{YELLOW}Press ANY KEY to roll a new number (Press 'q' or Ctrl+C to quit){RESET}\n")

    try:
        while True:
            formatted_num = roll_number(lower, upper, include_limits, is_decimal, decimals, lower_int, upper_int)

            # Overwrite line for clean terminal feel
            sys.stdout.write(f"\r🎲 Result: {BOLD}{CYAN}{formatted_num:<20}{RESET} (Press key...)")
            sys.stdout.flush()

            key = get_key()
            # Quit check: EOF, 'q', 'Q', or Ctrl+C (\x03)
            if not key or key in ['q', 'Q', '\x03']:
                break

    except KeyboardInterrupt:
        pass
    finally:
        print(f"\n\n{YELLOW}Exited generator.{RESET}\n")

def run_direct_cli():
    """Parses CLI arguments, skips question prompts, and starts generator directly."""
    if sys.argv[1] in ("-h", "--help"):
        print_help()
        sys.exit(0)

    if len(sys.argv) < 3:
        print(f"{RED}Error: Both lower-limit and upper-limit are required.{RESET}\n", file=sys.stderr)
        print_help()
        sys.exit(1)

    try:
        lower = float(sys.argv[1])
    except ValueError:
        print(f"{RED}Error: Lower limit must be a valid number.{RESET}", file=sys.stderr)
        sys.exit(1)

    try:
        upper = float(sys.argv[2])
    except ValueError:
        print(f"{RED}Error: Upper limit must be a valid number.{RESET}", file=sys.stderr)
        sys.exit(1)

    if lower > upper:
        print(f"{YELLOW}↳ Lower bound was greater than upper. Auto-swapping bounds!{RESET}")
        lower, upper = upper, lower
    elif lower == upper:
        print(f"{RED}Error: Lower and upper limits cannot be identical.{RESET}", file=sys.stderr)
        sys.exit(1)

    inc_choice = sys.argv[3] if len(sys.argv) > 3 else "1"
    include_limits = (inc_choice != "2")

    num_type = sys.argv[4] if len(sys.argv) > 4 else "1"
    is_decimal = (num_type == "2")

    decimals = 2
    lower_int = None
    upper_int = None

    if is_decimal:
        if len(sys.argv) > 5:
            try:
                decimals = int(sys.argv[5])
                if decimals < 0:
                    raise ValueError
            except ValueError:
                print(f"{RED}Error: Decimal places must be a non-negative integer.{RESET}", file=sys.stderr)
                sys.exit(1)
    else:
        lower_int = int(lower)
        upper_int = int(upper)
        if not include_limits:
            lower_int += 1
            upper_int -= 1

        if lower_int > upper_int:
            print(f"{RED}Error: No whole numbers exist in the specified range with current inclusion rules.{RESET}", file=sys.stderr)
            sys.exit(1)

    start_generator_loop(lower, upper, include_limits, is_decimal, decimals, lower_int, upper_int)

def run_interactive():
    """Runs interactive setup prompts before starting generator."""
    print(f"\n{BOLD}{CYAN}=== Interactive Terminal RNG ==={RESET}\n")

    # 1. Lower and Upper Limits
    lower = prompt_float(f"{BOLD}1. Enter Lower Limit: {RESET}")
    upper = prompt_float(f"{BOLD}   Enter Upper Limit: {RESET}")

    if lower > upper:
        print(f"{YELLOW}↳ Lower bound was greater than upper. Auto-swapping bounds!{RESET}")
        lower, upper = upper, lower
    elif lower == upper:
        print(f"{RED}Error: Lower and upper limits cannot be identical.{RESET}")
        return

    # 2. Including or Excluding limits
    print(f"\n{BOLD}2. Inclusion Mode:{RESET}")
    print("   [1] Inclusive (Include limits)")
    print("   [2] Exclusive (Exclude limits)")
    inc_choice = input(f"{BOLD}   Select (1/2, default=1): {RESET}").strip()
    include_limits = (inc_choice != "2")

    # 3. Whole or Decimal
    print(f"\n{BOLD}3. Number Type:{RESET}")
    print("   [1] Whole Numbers (Integers)")
    print("   [2] Decimal Numbers (Floats)")
    num_type = input(f"{BOLD}   Select (1/2, default=1): {RESET}").strip()
    
    is_decimal = (num_type == "2")
    decimals = 2
    lower_int = None
    upper_int = None

    if is_decimal:
        while True:
            try:
                decimals = int(input(f"{BOLD}   How many decimal places? (1-10): {RESET}"))
                if decimals >= 0:
                    break
            except ValueError:
                pass
            print(f"{RED}Please enter a valid positive integer.{RESET}")
    else:
        lower_int = int(lower)
        upper_int = int(upper)
        
        if not include_limits:
            lower_int += 1
            upper_int -= 1

        if lower_int > upper_int:
            print(f"\n{RED}Error: No whole numbers exist in the specified range with current inclusion rules.{RESET}")
            return

    # 4. Generator Loop
    start_generator_loop(lower, upper, include_limits, is_decimal, decimals, lower_int, upper_int)

def main():
    if len(sys.argv) > 1:
        run_direct_cli()
    else:
        run_interactive()

if __name__ == "__main__":
    main()
