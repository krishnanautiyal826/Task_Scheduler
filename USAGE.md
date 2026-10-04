# How to use Task Scheduler

Task Scheduler takes your tasks and tells you what order to do them in. A task can be marked as **waiting for** another task, and the plan always puts a task after the ones it waits for. When several tasks are ready at once, the one due soonest comes first.

You don't need to learn any commands. The program asks you questions and you type the answers.

## Start it

You need Python 3.9 or newer. Open a terminal in the project folder and run:

```
python main.py
```

(On some computers the command is `python3 main.py`.)

To see how it works before entering your own tasks, run `python main.py --demo`. That starts with five example tasks already loaded.

## A two-minute walkthrough

This is a real session, copied from the program. The text after each `?` or `:` is what the person typed; a blank means they just pressed Enter. After the first menu, the menu is left out to save space, but the program shows it every time.

Three tasks are added. Then the plan is shown. Then the person realises the report will take 4 days, not 2, and changes it.

```
Task Scheduler
Put your tasks in the right order, with the things they depend on first.
Type ? at the menu for help. Type 'cancel' at any question to stop.

What would you like to do?
  1  Add a task
  2  See my tasks
  3  Get my plan (what to do, in what order)
  4  Find what could delay everything
  5  Change a task
  6  Say that one task must wait for another
  7  Remove a task
  8  Remove a "must wait for" link
  9  Load an example
  10 Save my tasks
  0  Quit
Your choice: 1

Let's add a task.
What is the task called? Make slides
How important is it? 1 = low ... 5 = urgent [3]: 3
When is it due? (tomorrow, friday, 5 nov, 05/11/2026): 2 nov
Due date: Mon 02 Nov 2026
How many days will it take? [1]: 1
Added 'Make slides': due Mon 02 Nov 2026, importance 3/5, 1 day.

[menu shown here]
Your choice: 1

Let's add a task.
What is the task called? Write report
How important is it? 1 = low ... 5 = urgent [3]: high
When is it due? (tomorrow, friday, 5 nov, 05/11/2026): 5 nov
Due date: Thu 05 Nov 2026
How many days will it take? [1]: 2

Your other tasks:
  1. Make slides
Does it have to wait for any of these? Numbers or names, separated by commas (Enter for none): 1
Added 'Write report': due Thu 05 Nov 2026, importance 4/5, 2 days. Waits for: Make slides.

[menu shown here]
Your choice: 1

Let's add a task.
What is the task called? Send to manager
How important is it? 1 = low ... 5 = urgent [3]: urgent
When is it due? (tomorrow, friday, 5 nov, 05/11/2026): 6 nov
Due date: Fri 06 Nov 2026
How many days will it take? [1]: 1

Your other tasks:
  1. Make slides
  2. Write report
Does it have to wait for any of these? Numbers or names, separated by commas (Enter for none): 2
Added 'Send to manager': due Fri 06 Nov 2026, importance 5/5, 1 day. Waits for: Write report.

[menu shown here]
Your choice: 3

Your plan: 3 tasks, in the order to do them

1. Make slides
   due Mon 02 Nov 2026, importance 3/5, 1 day
2. Write report
   due Thu 05 Nov 2026, importance 4/5, 2 days
   after: Make slides
3. Send to manager
   due Fri 06 Nov 2026, importance 5/5, 1 day
   after: Write report

How the order is chosen: a task goes only after everything it waits for is done. When several are ready, the one due soonest goes first, then the more important one.

[menu shown here]
Your choice: 5

Your tasks:
  1. Make slides
  2. Write report
  3. Send to manager
Which task do you want to change? (number or name): Write report

Changing 'Write report': due Thu 05 Nov 2026, importance 4/5, 2 days.
Press Enter at any question to keep what it is now.
What is the task called? [Write report] 
How important is it? 1 = low ... 5 = urgent [4]: 
When is it due? (tomorrow, friday, 5 nov, 05/11/2026) [Thu 05 Nov 2026]: 
How many days will it take? [2]: 4

Your tasks:
  1. Make slides
  2. Write report   (this task)
  3. Send to manager
What does it wait for? Right now: Make slides.
Numbers or names separated by commas, 'none' for nothing, Enter to keep: 
Changed 'Write report':
  - days: 2 → 4

[menu shown here]
Your choice: 4

Longest chain: Make slides → Write report → Send to manager  (6 days)
If any task on this chain slips, everything finishes later.
That total assumes tasks that don't depend on each other happen at the same time. Doing one thing at a time, everything takes 6 days.

[menu shown here]
Your choice: 10
Saved 3 tasks to my_tasks.json.

[menu shown here]
Your choice: 0
Goodbye.
```

## The menu

| Choice | What it does |
|---|---|
| **1** Add a task | Asks for the name, importance, due date, how many days it takes, and what it has to wait for |
| **2** See my tasks | Lists every task with its details and what it waits for |
| **3** Get my plan | Shows the order to do things in, and explains it |
| **4** Find what could delay everything | Shows the longest chain of tasks that wait on each other |
| **5** Change a task | Fix the name, importance, due date, days, or what it waits for |
| **6** Say that one task must wait for another | Links two tasks you already added |
| **7** Remove a task | Deletes a task (it asks you to confirm) |
| **8** Remove a "must wait for" link | Undoes a link between two tasks |
| **9** Load an example | Fills the list with five example tasks (only works on an empty list) |
| **10** Save my tasks | Writes your tasks to a file so they are still there next time |
| **0** Quit | Exits (it offers to save first if you have unsaved changes) |

Type `?` at the menu for a short reminder. Type `cancel` at any question to stop what you're doing; nothing is changed.

## What the questions mean

- **Name.** Anything you like, including spaces. No commas, and not just a number.
- **Importance.** 1 is low and 5 is urgent. You can also type `low`, `medium`, `high` or `urgent`. Pressing Enter means 3.
- **Due date.** See the next section. The program repeats the date back to you so you can check it understood.
- **Days it will take.** A whole number of days. Pressing Enter means 1.
- **Waits for.** Pick the tasks that must be finished *before* this one can start. For example, "Send to manager" waits for "Write report". You can type numbers (`1,3`) or names (`make slides`), or press Enter if it waits for nothing.

## Typing dates

All of these work:

| You type | Meaning |
|---|---|
| `today`, `tomorrow` | |
| `friday`, `next monday` | The coming one. If today is Friday, `friday` means a week from today |
| `in 3 days`, `in 2 weeks` | |
| `5 nov`, `nov 5`, `5th November 2026` | Without a year, the coming 5 November |
| `05/11/2026`, `5-11-2026`, `5.11.2026` | **Day first**: this is 5 November, not May 11 |
| `2026-11-05` | Year first |

Dates are always read day first. If you type a date that has already passed, the program accepts it and tells you it has passed. A date that doesn't exist, such as `31 feb`, or one that is absurdly far away is refused and you are asked again.

## Reading your plan (menu 3)

```
2. Write report
   due Thu 05 Nov 2026, importance 4/5, 2 days
   after: Make slides
```

- The numbers give the order to do things in.
- **after:** lists the tasks that must be finished first.
- **The order is chosen like this.** A task only goes after everything it waits for. When several tasks are ready at the same time, the one due soonest goes first. If they are due on the same day, the more important one goes first.

**Heads-up lines.** Sometimes the plan prints a warning like this:

```
Heads-up: 'test' must be finished before 'deploy' can start, but 'test' is due
Fri 06 Nov 2026, later than 'deploy' (Sun 01 Nov 2026). One of those dates
probably needs to change.
```

It means two of your dates contradict each other: a task is due earlier than something it has to wait for. The plan still works, and the task that has to wait goes later, but you can't meet both dates. Fix it by changing one of the dates (menu 5).

## The longest chain (menu 4)

This shows the longest run of tasks that each wait for the one before. If any task on that chain slips, everything finishes later. The number of days assumes that tasks which don't depend on each other can happen at the same time. If you are doing everything yourself, one at a time, the program also shows that longer total.

## Changing a task (menu 5)

Choose the task by number or name. The program then asks the same questions as when adding a task, but each one shows what the task has now in square brackets, like `[Thu 05 Nov 2026]`. **Press Enter to keep a value**, or type a new one.

The last question is what the task waits for. It shows the current list. You can:

- press Enter to keep it as it is,
- type new numbers or names (for example `1, 3`) to replace the list,
- type `none` to make the task wait for nothing.

Things to know:

- **Nothing changes until you answer the last question.** If you type `cancel` part-way through, the task stays exactly as it was.
- **When you finish, it lists what changed**, for example `days: 2 → 4`. If you pressed Enter everywhere, it says "Nothing was changed".
- **Renaming is safe.** Every link to the task follows the new name, and it keeps its place in your list.
- **It won't let you create a loop.** If you make `build` wait for `deploy` but `deploy` already (directly or not) waits for `build`, you'll see:

```
'build' can't wait for 'deploy': 'deploy' already has to wait for 'build' (build → test → deploy), so they would wait on each other.
```

  and you are asked again.

## If you make a mistake

- **Wrong details on a task:** use menu **5**.
- **Added a task you didn't want:** use menu **7**.
- **Linked the wrong tasks:** use menu **8** to remove the link.
- **Two tasks waiting on each other:** the program refuses a link that would do this and shows the loop. If a loop comes from a file you loaded, the plan names the tasks in it; use menu **8** to remove one of the links.

## Saving

Your tasks live in memory until you save them.

- Choose **10** to save. The file is `my_tasks.json`, in the folder you started the program from.
- When you quit with unsaved changes, it asks whether to save first.
- Next time you start, if it finds `my_tasks.json` it asks whether to load it.
- **It will not quietly replace a saved list.** If `my_tasks.json` already holds tasks that you chose not to load, saving asks first ("already holds 5 saved tasks that are not in your current list. Replace them?") and the answer defaults to **no**.
- Saving never overwrites a file you opened with `--file`, or the built-in example. It always writes to `my_tasks.json`.

## Loading tasks from a file

```
python main.py --file examples/tasks.json
```

The file format is in `examples/tasks.json`: a list of tasks (`id`, `priority`, `deadline` as `YYYY-MM-DD`, optional `duration`) and a list of `["task", "waits for"]` pairs. A file that can't be read is reported in plain words and the program exits without changing anything.

## Typed commands (advanced)

If you prefer typing commands to answering questions, run `python main.py --commands`. Type `help` to see them. They include `edit <task> <field> <value>`, where the field is `name`, `priority`, `deadline` or `days`. For example: `edit build days 4`. Typed mode can't remove a link or change what a task waits for; use the menu for that. The commands are listed in the README.

## Common questions

**Why is a task with an early due date listed late?**
Because it waits for something else. Dependencies come before due dates. The plan prints a heads-up when this happens because the dates disagree.

**Does the plan guarantee I'll meet my deadlines?**
No. It orders the tasks correctly, but it doesn't know how many people are working or how many hours you have. The number of days a task takes is only used by menu 4.

**Does it handle two people working at once?**
No. The plan is a single list. Menu 4 assumes unlimited parallel work, which tells you the fastest possible finish, not what one person can do.

**Where did my tasks go?**
If you didn't choose 10 (or answer `y` when you quit), they were not saved. Look for `my_tasks.json` in the folder you ran the program from.

**Can I use names with spaces?**
Yes. Names and numbers can both be used when picking from a list, in any capitalisation. A number always means the position in the list that was just shown.
