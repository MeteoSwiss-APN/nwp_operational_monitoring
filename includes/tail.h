end_time=$(date +%%s)
TASK_DURATION=$((end_time - start_time))
ecflow_client --label=duration "${TASK_DURATION}s"

set +e
set +u


echo "$TASK_DURATION"
ecflow_client --complete

curl -X POST \
  -H "Authorization: Bearer $GRAFANA_TOKEN" \
  -H "Content-Type: text/plain" \
  "$GRAFANA_URL" \
  -d "ecflow_task_duration,task=$ECF_NAME value=$TASK_DURATION"

