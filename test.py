import os
from ecflow import *

home = os.path.join(os.getenv("HOME"), "course")


defs = Defs(
Suite("test",

    Family("main",

        Task(
            "t1",
            Label("duration", ""),
            Late(complete="00:01"),
            Meter("progress", 0, 50)

        ),

        Task(
            "t2",
            Label("duration", ""),
            Late(complete="00:01")
        ),

        Task(
            "notify_late",
            Trigger("t2<flag>late")
        ),

        Task(
            "check_meter",
            Trigger("t1 == active")
        )


    ),

    Edit(
        ECF_HOME=home,
        ECF_INCLUDE=os.path.join(home, "includes"),
        ECF_FILES=os.path.join(home, "scripts"),
    )
))
print(defs.check_job_creation())
defs.save_as_defs("test.def")
