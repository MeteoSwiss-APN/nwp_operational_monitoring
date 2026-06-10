#!%SHELL:/bin/ksh%
set -e          # stop the shell on first error
set -u          # fail when using an undefined variable
set -x          # echo script lines as they are executed


# Defines the variables that are needed for any communication with ECF
export ECF_PORT=%ECF_PORT%    # The server port number
export ECF_HOST=%ECF_HOST%    # The host name where the server is running
export ECF_NAME=%ECF_NAME%    # The name of this current task
export ECF_PASS=%ECF_PASS%    # A unique password, used for job validation & zombie detection
export ECF_TRYNO=%ECF_TRYNO%  # Current try number of the task
export ECF_RID=$$             # record the process id. Also used for zombie detection
# export NO_ECF=1             # uncomment to run as a standalone task on the command line

# Load credentials
source %ECF_INCLUDE%/.credentials

# Tell ecFlow we have started
start_time=$(date +%%s)
ecflow_client --init=$$

# Define a error handler
ERROR() {

   trap - ERR
   set +e
   set +u
   curl -X POST "$GRAFANA_URL"\
     -H "Authorization: Bearer $GRAFANA_TOKEN" \
     -d "ecflow_task_failure,task=$ECF_NAME value=1"

   sleep 2
   ecflow_client --abort=trap

   exit 0
}


trap 'ERROR' ERR

# Trap any signal that may cause the script to fail
trap '{ echo "Killed by a signal"; ERROR ; }' 1 2 3 4 5 6 7 8 10 12 13 15
