# Club Event Signup

## Purpose

This is a design for a pretend signup screen for the **Riverside Otters Swim Club**, a fictional swimming club. A visitor types a made-up attendee name, picks one of two swim sessions, and presses a button to see a confirmation message.

This is only a prototype that runs on its own in the browser. It does **not** do real registration. It has no accounts, no server, no network requests, and it does not save anything. Nothing is remembered: if the page is refreshed or closed, it goes back to its starting state. Users should only type fictional names, never real personal information.

## Screen

There is one screen. From top to bottom it shows:

1. **Title:** "Club Event Signup", shown as the largest text on the page.
2. **Club name:** "Riverside Otters Swim Club", in smaller text just below the title.
3. **Instructions:** "Enter a fictional attendee name, choose one session, then press Sign Up."
4. **Name field:** a one-line text box. Its label, shown just above the box, is "Attendee name (fictional)".
5. **Session choices:** a group labeled "Choose a session", with two round option buttons (radio buttons) in a column. Only one can be picked at a time:
   - "Beginner Lesson"
   - "Advanced Practice"
6. **Sign Up button:** one main button with the text "Sign Up". This is the only button on the screen.
7. **Message area:** a space directly below the Sign Up button where success and error messages appear. It is empty until the button is pressed.

**Colors**

- Page background: white (#FFFFFF).
- Title, and the Sign Up button's background: navy blue (#1F3A5F).
- Sign Up button text: white (#FFFFFF).
- Club name, instructions, labels, and normal text: dark gray (#333333).
- Name field border: medium gray (#767676).
- Success message text: dark green (#1B5E20).
- Error message text: dark red (#B00020).

All text has strong contrast against its background so it is easy to read. Messages never rely on color alone: the words themselves say whether it is a success ("Success!") or a problem ("Please...").

**Typography**

- One simple sans-serif font, such as Arial, everywhere.
- Title: 28 px, bold. Club name: 20 px.
- Instructions, labels, choices, messages, and button text: at least 16 px.
- Labels are bold, so it is clear which control each label belongs to.
- Each session's label text can be clicked to pick that session, not just the small circle.

**Keyboard use**

- The Tab key moves through the screen in this order: name field, then the session group, then the Sign Up button.
- Inside the session group, the arrow keys move between "Beginner Lesson" and "Advanced Practice", and the Space key picks the one that has focus.
- When the Sign Up button has focus, pressing Enter or Space presses it.
- Pressing Enter while typing in the name field does the same thing as pressing Sign Up.
- Whatever has keyboard focus shows a clear navy outline, so keyboard users can see where they are.

**Starting state**

When the page first opens (or is refreshed):

- The name field is empty.
- No session is selected.
- The message area is empty: no success message and no error message.

## Behavior

When the user presses **Sign Up** (or presses Enter in the name field), the screen checks the two inputs:

- **Name check:** spaces at the start and end of the name are ignored. If anything is left, the name is valid.
- **Session check:** the session is valid if "Beginner Lesson" or "Advanced Practice" is selected.

Every time Sign Up is pressed, whatever was in the message area before is removed first. Then exactly one new result is shown there.

**If both are valid**, the message area shows this confirmation, in dark green:

> Success! [name] is signed up for [session].

- [name] is the name as typed, with spaces at the start and end removed.
- [session] is the selected session, written exactly as its label ("Beginner Lesson" or "Advanced Practice").
- Example: "Success! Mia Lopez is signed up for Beginner Lesson."

After a success, the name field keeps the name and the selected session stays selected. Nothing is cleared, so the user can easily sign the same person up for the other session.

**When an old confirmation disappears:** a confirmation goes away as soon as the user changes the name field or picks a different session. That way the screen never shows a confirmation that no longer matches what is on the screen. The message area then stays empty until Sign Up is pressed again, when the new result appears. A confirmation also disappears if the page is refreshed, because nothing is saved.

## Missing or invalid input

A success message is **never** shown if either input is invalid. Error messages appear in the same message area, directly below the Sign Up button, in dark red.

**Empty or whitespace-only name**

If the name field is empty, or has only spaces in it, the name is invalid. The message area shows:

> Please enter an attendee name.

**No session selected**

If no session is selected, the message area shows:

> Please choose a session.

**Both missing**

If the name is invalid **and** no session is selected, both errors are shown, each on its own line, name error first:

> Please enter an attendee name.
> Please choose a session.

**What is kept when there is an error**

- Nothing the user entered is erased.
- If the session was valid but the name was not, the selected session stays selected while the user fixes the name.
- If the name was valid but no session was picked, the name stays in the field while the user picks a session.
- After an error, the keyboard focus moves to the first input that needs fixing: the name field if the name is invalid, or else the session group.

**How to fix and try again**

1. Read the error message below the Sign Up button.
2. Type a real-looking fictional name in the name field, and/or pick a session.
3. Press Sign Up again.

Error messages stay on screen while the user is fixing things. They are replaced when Sign Up is pressed again: by a success message if everything is now valid, or by the current error message(s) if something is still wrong.

## Examples to check

**Example 1: Successful signup**

- Start: the page has just opened (empty name, no session, empty message area).
- Input: type `Mia Lopez` in the name field. Select "Beginner Lesson".
- Action: press Sign Up.
- Expected result: the message area below the button shows, in dark green:
  "Success! Mia Lopez is signed up for Beginner Lesson."
  The name field still says "Mia Lopez" and "Beginner Lesson" is still selected.

**Example 2: Name with only spaces**

- Start: the page has just opened.
- Input: type three spaces in the name field. Select "Advanced Practice".
- Action: press Sign Up.
- Expected result: the message area below the button shows, in dark red:
  "Please enter an attendee name."
  No success message appears. "Advanced Practice" is still selected. The name field still holds the three spaces, and keyboard focus moves to the name field so the user can fix it.

**Example 3: Change the session after a success**

- Start: the end of Example 1. The name field says "Mia Lopez", "Beginner Lesson" is selected, and the message area shows "Success! Mia Lopez is signed up for Beginner Lesson."
- Action 1: select "Advanced Practice".
- Expected result 1: the old confirmation disappears and the message area is empty. The name field still says "Mia Lopez".
- Action 2: press Sign Up.
- Expected result 2: the message area below the button shows, in dark green:
  "Success! Mia Lopez is signed up for Advanced Practice."
  The old "Beginner Lesson" confirmation is not shown anywhere. The name field still says "Mia Lopez" and "Advanced Practice" is selected.
