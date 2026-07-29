# =====================================================================
#  ⚔️  OPERATION: CODE WARRIOR — STAGE 1: ARTILLERY STRIKE
# =====================================================================
#  YOUR MISSION:
#  An enemy bunker is hidden somewhere on a battle line, at a position
#  between 1 and 100. You command an artillery gun with a limited
#  number of shells. Fire at a position; your radar tells you if the
#  shot OVERSHOT (too far) or FELL SHORT (too close). Destroy the
#  bunker before you run out of shells.
#
#  HOW TO READ THIS FILE:
#  - Lines starting with '#' are COMMENTS: notes for humans.
#    The computer completely ignores them.
#  - Technical words are in CAPITALS the first time they appear.
#    These are the words real programmers use every day.
#  - The computer reads this file TOP TO BOTTOM, like you reading
#    orders. That top-to-bottom flow is called EXECUTION.
# =====================================================================


# --- IMPORTING A MODULE ---------------------------------------------
# A MODULE is pre-written code we borrow instead of writing ourselves.
# Think of it as calling in an allied unit. 'random' is a module that
# knows how to pick unpredictable numbers — perfect for hiding a bunker.
import random


# --- DEFINING FUNCTIONS ---------------------------------------------
# A FUNCTION is a named, reusable block of orders — like a drilled
# maneuver. You define it once ('def' = define), then execute it by
# name whenever you want. Nothing inside runs until it is CALLED.

def fire_mission():
    # This function plays ONE complete battle (one round).

    # --- VARIABLES ---
    # A VARIABLE is a labeled crate that stores a value.
    # The '=' sign means "store this value under this name"
    # (it does NOT mean 'equals' like in math).
    bunker = random.randint(1, 100)   # secret enemy position (an INTEGER: a whole number)
    shells = 7                        # your ammo supply
    shots_fired = 0                   # counter, starts at zero

    # print() sends text to the screen. Text in quotes is a STRING.
    print()
    print("📡 RADAR: Enemy bunker detected on the battle line (1-100).")
    print(f"🧨 You have {shells} shells. Make them count, Commander.")
    # That f before the quote makes an F-STRING: it lets us inject
    # the VALUE of a variable into text using {curly_braces}.

    # --- THE LOOP ---
    # A LOOP repeats orders until told to stop. 'while' means
    # "keep repeating as long as this condition is True".
    # Here: keep fighting while we still have shells left.
    while shells > 0:

        # input() PAUSES the program and waits for the user to type.
        # Whatever they type arrives as a STRING (text), even "42".
        raw = input(f"\n🎯 Fire at position (1-100) [{shells} shells left]: ")

        # --- INPUT VALIDATION: your first security habit -----------
        # 🛡️ NEVER TRUST USER INPUT. This is the #1 rule in both
        # programming AND security. If the user types "banana",
        # converting it to a number would CRASH the program.
        # A crash caused by bad input is exactly how many real
        # hacks begin: attackers feed programs input the programmer
        # never expected, and use the failure to break in.
        #
        # try/except is our gate guard: TRY the risky move, and if it
        # fails (raises a ValueError), CATCH the error instead of dying.
        try:
            target = int(raw)         # int() converts STRING -> INTEGER
        except ValueError:
            print("⚠️  FIRE CONTROL: Numbers only, Commander. Shell not wasted.")
            continue                  # 'continue' = skip back to the top of the loop

        # A second validation layer: the number must be in range.
        # Good security is LAYERED — one gate is never enough.
        if target < 1 or target > 100:
            print("⚠️  FIRE CONTROL: Position must be 1-100. Shell not wasted.")
            continue

        # Valid shot — spend a shell, count the shot.
        shells = shells - 1           # subtract 1 from the crate's value
        shots_fired += 1              # '+=' is shorthand for the same idea

        # --- CONDITIONALS: the fork in the road ---------------------
        # 'if / elif / else' lets the program make decisions.
        # Exactly ONE of these branches will run.
        if target == bunker:          # '==' asks "are these equal?" (compare, don't confuse with '=')
            print()
            print("💥💥💥 DIRECT HIT! Bunker destroyed! 💥💥💥")
            print(f"🎖️  Victory in {shots_fired} shots.")
            return True               # 'return' exits the function and hands back a value
        elif target > bunker:
            print("📡 RADAR: OVERSHOT — the bunker is CLOSER than that.")
        else:
            print("📡 RADAR: FELL SHORT — the bunker is FARTHER than that.")

        # Tension: a smart hint when running low.
        if shells == 1:
            print("🚨 LAST SHELL. Steady, Commander...")

    # If the loop ends without a 'return', we ran out of shells.
    print()
    print("☠️  OUT OF AMMO. The bunker survives... this time.")
    print(f"🕵️  Intel report: the bunker was at position {bunker}.")
    return False                      # False/True are BOOLEANS: two-position switches


def main():
    # The main function runs the whole campaign: rounds + score.
    print("=" * 55)                   # a STRING can be multiplied: '=' repeated 55 times
    print("   ⚔️  OPERATION: CODE WARRIOR — ARTILLERY STRIKE ⚔️")
    print("=" * 55)

    victories = 0
    battles = 0
    campaigning = True                # a BOOLEAN switch controlling the outer loop

    while campaigning:
        won = fire_mission()          # CALL the function; catch its returned Boolean
        battles += 1
        if won:
            victories += 1

        print(f"\n🏅 CAMPAIGN SCORE: {victories} victories in {battles} battles.")

        again = input("\nAnother fire mission? (y/n): ")
        # .lower() converts text to lowercase, so 'Y' and 'y' both work.
        # Handling messy human input gracefully = good engineering.
        if again.lower() != "y":      # '!=' asks "are these NOT equal?"
            campaigning = False       # flip the switch; the loop ends

    print("\n🫡  Dismissed. Well fought, Commander.")


# --- THE STARTING GUN ------------------------------------------------
# Defining functions loads the maneuvers into memory, but nothing
# happens until something CALLS them. This line starts the war:
main()


# =====================================================================
#  🛡️  SECURITY DEBRIEF — STAGE 1
# =====================================================================
#  Today you learned INPUT VALIDATION (the try/except and range check).
#  Here is why that tiny habit matters in the real world:
#
#  Every program has GATES where outside data comes in — a keyboard,
#  a file, a network connection. Attackers don't break walls; they
#  walk through unguarded gates carrying input the programmer never
#  imagined. Feeding a program hostile input to make it misbehave is
#  the root of most famous attacks (buffer overflows, SQL injection —
#  you'll meet these by name in later stages).
#
#  Your PC-level takeaways this week (see SECURITY-BRIEFING.md):
#   1. UPDATES ARE ARMOR. Software updates are mostly patched gates —
#      holes someone found. Install them fast, on phone and PC.
#   2. ANTIVIRUS is your radar; keep Windows Defender (or similar) ON.
#   3. Downloads are incoming shells: only run programs from sources
#      you trust, because RUNNING a program = giving it your authority.
#
#  🎯 DRILLS (do these — typing is how you remember):
#   1. Change shells = 7 to shells = 5. Harder war.
#   2. Change the battle line to 1-200. What ELSE must you update?
#      (Hint: the messages and the range check — code has to stay
#      consistent, and finding every spot is real programmer work.)
#   3. Add a taunt when the player misses by a lot:
#         if target > bunker + 30:
#             print("📡 RADAR: Not even close, Commander.")
#      Where must that go so 'bunker' and 'target' both exist?
#   4. BREAK IT ON PURPOSE: remove the try/except and type 'banana'.
#      Read the crash message (called a TRACEBACK). Congratulations —
#      you just performed your first vulnerability test.
# =====================================================================
