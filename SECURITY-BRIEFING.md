# 🛡️ THE WAR ROOM SECURITY BRIEFING

*How hacking actually works, explained like the war it is — and how to
defend your PC today and your servers later.*

You don't need to finish the coding stages to read this. But each
coding stage will make one section below click harder, because you'll
have **built the gate that attackers walk through**.

---

## 1. The big picture: every computer is a fort

- Your **PC, phone, or server** is a fort.
- **Programs** are the soldiers inside, each with orders (code).
- **Data** (photos, passwords, files) is the treasure in the vault.
- Every way data can enter — keyboard, Wi-Fi, USB stick, email,
  downloads, open network ports — is a **GATE**.

The sum of all your gates has a technical name: the **ATTACK SURFACE**.
Defense in one sentence: **know your gates, guard your gates, and keep
your gate count small.**

Attackers almost never "smash walls" like in movies. They:
1. **Scan** for gates you forgot about (open ports, old software).
2. **Trick a guard** into opening one (phishing — see below).
3. **Feed a gate weird input** its programmer never expected
   (exactly what your Stage 1 `try/except` defends against).

---

## 2. Know your enemy: the malware bestiary

**MALWARE** = *mal*icious soft*ware*. Umbrella word for all hostile code.

| Enemy | War analogy | What it actually does |
|-------|-------------|----------------------|
| **VIRUS** | A saboteur who hides inside a legitimate supply crate | Attaches itself to a real file/program; spreads when that file is shared or run |
| **WORM** | A saboteur who needs no crate — he crawls between forts on his own | Spreads across networks automatically, no human click needed |
| **TROJAN (Trojan horse)** | The famous gift horse: looks like a present, soldiers inside | A program that *pretends* to be useful ("Free Game.exe!") so YOU invite it in |
| **RANSOMWARE** | Enemy locks your own vault and sells you the key | Encrypts your files, demands payment to unlock them |
| **SPYWARE / KEYLOGGER** | A spy in your ranks copying every order you write | Silently records your keystrokes, passwords, screen |
| **BOTNET** | Your fort captured and forced to fight in the enemy's army | Your infected PC secretly attacks others on a hacker's command |
| **ROOTKIT** | A traitor wearing a general's uniform | Malware that hides deep in the system with admin ("root") authority, invisible to normal inspection |

**The key insight:** malware is just *code*, like your game — except its
`main()` serves the attacker. That's why "where did this code come from
and who wrote it?" is THE question before running anything.

---

## 3. The human gate: phishing & social engineering

The strongest fort falls if a guard opens the gate. **SOCIAL
ENGINEERING** = manipulating people instead of machines. **PHISHING** =
fake messages (email/SMS/WhatsApp) impersonating someone you trust:
your bank, "Microsoft", a delivery company.

Their weapons are **urgency and fear**: *"Your account will be locked
in 24 hours! Click here!"* Urgency is designed to switch off your
thinking. Real organizations rarely demand instant clicks.

**Standing orders:**
- Never click links in unexpected messages. Go to the website yourself
  by typing the address.
- Check the sender's actual address, not the display name.
- No legitimate service will ever ask for your password in a message.
- When in doubt: slow down. Urgency IS the attack.

---

## 4. Your PC's defense plan (do these THIS WEEK)

Think of it as fortifying your base — in priority order:

1. **UPDATES = ARMOR PLATING.** Most updates patch security holes that
   are already publicly known. An un-updated PC is a fort whose
   weaknesses are published in the enemy's newspaper. Turn on
   automatic updates for your OS, browser, and phone.
2. **ANTIVIRUS = RADAR.** Windows Defender (built into Windows) is
   genuinely good — make sure it's ON. Don't install five antivirus
   apps; one good radar beats five squabbling ones.
3. **PASSWORDS = GATE KEYS.** One reused password means one captured
   key opens ALL your forts. Use long passphrases (`correct-horse-
   battery-staple` style) and a **PASSWORD MANAGER** so every site
   gets its own key.
4. **2FA / MFA (two-factor authentication) = TWO GUARDS AT THE GATE.**
   Even with your stolen password, the attacker also needs your phone.
   Enable it on email and banking first — email is the master gate,
   because "reset password" links go there.
5. **BACKUPS = A SECOND FORT.** Ransomware is powerless if your
   treasure also lives somewhere else. Back up important files to a
   cloud drive or external disk. Rule of thumb: **3-2-1** — 3 copies,
   2 different types of storage, 1 kept off-site.
6. **DOWNLOADS = INCOMING PACKAGES.** Only install from official
   stores/sites. "Free" cracked software is the classic Trojan horse.
7. **FIREWALL = THE OUTER WALL.** It blocks unsolicited network
   connections. Windows/Mac have one built in — keep it on. (You'll
   truly understand it in Stage 6 when you open a port yourself.)
8. **PUBLIC WI-FI = ENEMY TERRITORY.** Assume someone may be
   listening. Fine for reading news; avoid banking. A **VPN**
   (encrypted tunnel) helps; HTTPS (the padlock) is your minimum.

---

## 5. PC ➜ SERVER: the road ahead

A **SERVER** is just a computer whose *job* is to answer strangers —
so its gates are open to the whole internet ON PURPOSE. That's why
server defense is stricter, and why stages 6–7 of the game teach it:

| Server concept | War analogy | You'll build it in |
|----------------|-------------|--------------------|
| **PORT** | A numbered gate in the wall (web = port 443) | Stage 6 |
| **PORT SCANNING** | Enemy scouts probing every gate to see which open | Stage 6 |
| **FIREWALL RULES** | "Only gate 443 opens; all others sealed" | Stage 6 |
| **AUTHENTICATION** | "Halt — password and papers" (who are you?) | Stage 6–7 |
| **AUTHORIZATION** | "Your rank doesn't allow entry to the armory" (what may you do?) | Stage 7 |
| **SQL INJECTION** | A forged order slipped into a normal message — the #1 web attack, and it's just Stage 1's "never trust input" at server scale | Stage 7 |
| **HTTPS / ENCRYPTION** | Sealed envelopes couriers can't read | Stage 5 & 7 |
| **LEAST PRIVILEGE** | Every soldier gets the minimum authority to do their job — so one captured soldier can't surrender the fort | Stage 3 & 7 |

---

## 6. The one-line summary of all cybersecurity

> **Every attack is either a hole in the code, or a trick on a human.
> Patch the code, train the human.**

You are now doing both: the coding stages patch-proof your future code,
and this briefing trains the human. Fight on, Commander. 🫡
