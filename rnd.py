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
    except ImportError:
        # Fallback for Windows
        import msvcrt
        return msvcrt.getch().decode('utf-8', errors='ignore')

def prompt_float(prompt_msg):
    while True:
        try:
            return float(input(prompt_msg))
        except ValueError:
            print(f"{RED}Invalid input. Please enter a valid number.{RESET}")

def main():
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

    if is_decimal:
        while True:
            try:
                decimals = int(input(f"{BOLD}   How many decimal places? (1-10): {RESET}"))
                if decimals >= 0:
                    break
            except ValueError:
                pass
            print(f"{RED}Please enter a valid positive integer.{RESET}")

    # Validate range for Whole Numbers
    if not is_decimal:
        lower_int = int(lower)
        upper_int = int(upper)
        
        if not include_limits:
            lower_int += 1
            upper_int -= 1

        if lower_int > upper_int:
            print(f"\n{RED}Error: No whole numbers exist in the specified range with current inclusion rules.{RESET}")
            return

    # 4. Interactive Loop
    print(f"\n{GREEN}✔ Configuration locked!{RESET}")
    print(f"{YELLOW}Press ANY KEY to roll a new number (Press 'q' or Ctrl+C to quit){RESET}\n")

    try:
        while True:
            if is_decimal:
                val = random.uniform(lower, upper)
                if not include_limits:
                    # Reroll if exact bound hit
                    while val == lower or val == upper:
                        val = random.uniform(lower, upper)
                formatted_num = f"{val:.{decimals}f}"
            else:
                formatted_num = str(random.randint(lower_int, upper_int))

            # Overwrite line for clean terminal feel
            sys.stdout.write(f"\r🎲 Result: {BOLD}{CYAN}{formatted_num:<20}{RESET} (Press key...)")
            sys.stdout.flush()

            key = get_key()
            # Quit check: 'q', 'Q', or Ctrl+C (\x03)
            if key in ['q', 'Q', '\x03']:
                break

    except KeyboardInterrupt:
        pass
    finally:
        print(f"\n\n{YELLOW}Exited generator cleanly.{RESET}\n")

if __name__ == "__main__":
    main()
