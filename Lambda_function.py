import json
import boto3
import datetime
import os
import requests
import re

s3 = boto3.client('s3')
ec2 = boto3.client('ec2')
bucket_name = 'ai-health-agent'  # Change if your bucket has a different name

def lambda_handler(event, context):
    print("Received event: " + json.dumps(event, indent=2))
    
    # Prepare report filename with timestamp
    now = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H-%M-%SZ')
    key_raw = f'incident-reports/incident_{now}.json'
    key_summary = f'incident-reports/incident_summary_{now}.txt'
    key_cost = f'incident-reports/cost_optimization_{now}.txt'
    key_remediate = f'incident-reports/remediation_{now}.txt'

    # Save raw event to S3
    s3.put_object(
        Bucket=bucket_name,
        Key=key_raw,
        Body=json.dumps(event, indent=2)
    )
    
    # Extract CloudWatch alarm details for summary and remediation
    try:
        message = event['Records'][0]['Sns']['Message']
    except Exception:
        message = str(event)
    
    # --- Remediation: Try to extract EC2 instance ID and reboot it ---
    instance_id = None
    remediation_result = "No remediation performed."
    try:
        match = re.search(r'Instance\s(i-[a-zA-Z0-9]+)', message)
        if match:
            instance_id = match.group(1)
            ec2.reboot_instances(InstanceIds=[instance_id])
            remediation_result = f"Instance {instance_id} rebooted by Lambda."
        else:
            remediation_result = "No instance ID found in the alert message."
    except Exception as e:
        remediation_result = f"Failed to remediate: {e}"
    
    # --- Generate AI summary and cost optimization using OpenAI ---
    api_key = os.environ.get('OPENAI_API_KEY')
    prompt = (
        f"Summarize this AWS incident and suggest possible remediations:\n\n{message}\n\n"
        "Also provide suggestions for optimizing AWS cloud costs related to this incident, "
        "and give best practices to prevent unnecessary spend (for example, right-sizing, auto-scaling, "
        "using spot instances, or stopping unused resources)."
    )
    ai_content = "AI response not available."
    summary = "AI summary not available."
    cost_advice = "Cost optimization suggestion not available."

    if api_key:
        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-3.5-turbo",
                    "messages": [
                        {"role": "system", "content": "You are an expert AWS cloud architect and FinOps cost optimization advisor."},
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": 400
                }
            )
            ai_content = response.json()["choices"][0]["message"]["content"]
            # For demo, save same content as summary and cost advice, or split if needed
            summary = ai_content
            cost_advice = ai_content
        except Exception as e:
            summary = f"Error getting AI summary: {e}"
            cost_advice = f"Error getting cost suggestion: {e}"

    # Save AI summary, cost advice, and remediation result to S3
    s3.put_object(
        Bucket=bucket_name,
        Key=key_summary,
        Body=summary
    )
    s3.put_object(
        Bucket=bucket_name,
        Key=key_cost,
        Body=cost_advice
    )
    s3.put_object(
        Bucket=bucket_name,
        Key=key_remediate,
        Body=remediation_result
    )
    
    print(remediation_result)
    return {
        'statusCode': 200,
        'body': json.dumps(f'Incident report, AI summary, cost optimization, and remediation: {remediation_result}')
    }