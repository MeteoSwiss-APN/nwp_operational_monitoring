# How to use it
Prerequisites:
- conda
- ecflow
  
Before using the files in this repository one has to first prepare the environment like following:

```bash
source /..../conda.sh
conda activate ecflow_5.11.3
export PATH=/envs/ecflow_5.11.3/bin:$PATH
ecflow_start.sh
```

The last line start the server. Once you have run the command, several lines will be printed. You will need to retrieve the Host and Port information from within the output lines that are displayed and execute:

```bash
export ECF_PORT=...
export ECF_HOST=...
```

It is also necessary to add a hidden file with the Grafana credentials inside the includes folder (.credentials).
Once the setup is complete, execute the following commands to start the task.

```bash
python test.py

ecflow_client --delete=yes /test
ecflow_client --load=test.def
ecflow_client --begin=/test
```
