import os
from ecflow import *

home = os.path.join(os.getenv("HOME"), "course")

scripts = os.path.join(home, "scripts")

# Create symlinks for the generic notify script
tasks_to_monitor = [
    ("t1", "main"),
    ("t2", "main"),
    ("t3", "main"),
    ("t4", "second"),
]

for task, _ in tasks_to_monitor:
    target = os.path.join(scripts, "notify_late.ecf")
    link = os.path.join(scripts, f"{task}_late_monitor.ecf")

    if os.path.lexists(link):
        os.remove(link)

    os.symlink(target, link)



def late_monitor(task, family):
    return Task(
        f"{task}_late_monitor",
        Trigger(f"{task}<flag>late"),
        Edit(
            TASK_PATH=f"/test/{family}/{task}"
        )
    )

defs = Defs(
Suite("test",

    Family("main",
        Task("main_start", Edit(SKIP_SPAN="1")),

        Task(
            "t1",
            Trigger("main_start == complete"),
            Label("duration", ""),
            Late(complete="+00:01")

        ),

        Task(
            "t2",
            Trigger("t1 == complete"),
            Label("duration", ""),
            Late(complete="+00:01")
        ),

        Task(
            "t3",
            Trigger("t2 == complete"),
            Label("duration", ""),
            Late(complete="+00:01")
        ),

        Task(
             "main_end",
             Trigger("t3 == complete"),
             Edit(SKIP_SPAN="1",FAMILY_PATH="/test/main")
         ),
        late_monitor("t1", "main"),
        late_monitor("t2", "main"),
        late_monitor("t3", "main"),


    ),

    Family("second",
        Trigger("/test/main/main_end == complete"),
        Task("second_start", Edit(SKIP_SPAN="1")),
        
        Task(
            "t4",
            Label("duration", ""),
            Late(complete="+00:01")

        ),
        Task(
            "second_end",
            Trigger("t4 == complete"),
            Edit(SKIP_SPAN="1", FAMILY_PATH="/test/second")
        ),

        late_monitor("t4", "second"),


    ),

    Edit(
        ECF_HOME=home,
        ECF_INCLUDE=os.path.join(home, "includes"),
        ECF_FILES=os.path.join(home, "scripts"),
    )
))
print(defs.check_job_creation())
defs.save_as_defs("test.def")
