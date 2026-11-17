# MuleWatch — AWS Deployment

## Architecture

MuleWatch uses a cost-conscious AWS deployment architecture.

### Application

- Amazon EC2 runs Docker Compose.
- Amazon ECR stores versioned container images.
- Caddy terminates HTTPS.
- The web frontend and FastAPI backend run in containers.
- The scoring service uses the registered ML model.
- The SQS worker processes incoming pipeline messages.

### Database

- Amazon RDS for PostgreSQL with pgvector.
- RDS is not publicly accessible.
- PostgreSQL access is restricted to the EC2 security group.
- Encryption at rest and automated backups are enabled.

### Event-Driven Pipeline

1. A CSV file is uploaded to the S3 landing bucket.
2. An S3 event invokes AWS Lambda.
3. Lambda validates the file.
4. Invalid files move to the quarantine prefix.
5. Valid files produce an Amazon SQS message.
6. The EC2 worker consumes the message.
7. The worker executes ingest, features, score and alerts.
8. Failed messages move to a dead-letter queue after three failed receives.

### Security and Operations

- EC2, Lambda and GitHub Actions use scoped IAM roles.
- GitHub Actions authenticates to AWS through OIDC.
- Application secrets are stored in SSM Parameter Store.
- CloudWatch collects logs and monitors failures.
- AWS Budgets provides spending alerts.
- EC2 access uses SSM Session Manager instead of SSH.

### Architecture Diagram

    Internet
       |
      HTTPS
       |
    Caddy (EC2)
       |
       +-- Web
       +-- FastAPI
       +-- Scoring
       +-- SQS Worker
               |
               +---- Private RDS PostgreSQL + pgvector

    S3 Landing
       |
    Lambda Validation
       |
       +-- Invalid --> S3 Quarantine
       |
       +-- Valid --> SQS Queue --> EC2 Worker
                        |
                        +--> Dead-Letter Queue

    ECR --> Container Images
    SSM --> Application Secrets
    CloudWatch --> Logs and Alarms
    AWS Budgets --> Cost Alerts

## Monthly Cost Estimate

Region: To be selected.

| AWS Service | Monthly Estimate |
|---|---|
| EC2 small instance | Pending AWS Pricing Calculator |
| RDS PostgreSQL micro | Pending AWS Pricing Calculator |
| Amazon S3 | Pending AWS Pricing Calculator |
| AWS Lambda | Pending AWS Pricing Calculator |
| Amazon SQS | Pending AWS Pricing Calculator |
| Amazon CloudWatch | Pending AWS Pricing Calculator |
| **Total** | **Pending** |

The estimate must be calculated before paid infrastructure is activated.

## Deployment Status

- Architecture documentation: Prepared
- Cost estimate: Pending
- AWS budget alarm: Pending account creation
- IAM roles: Pending
- ECR repositories: Pending
- S3 buckets: Pending
- SSM SecureString parameters: Pending

## Teardown Plan

When the demonstration is no longer needed:

1. Preserve required application artifacts and backups.
2. Stop and terminate EC2 after confirming data is preserved.
3. Delete RDS after confirming snapshot and retention requirements.
4. Remove unused S3 objects and buckets.
5. Remove unused ECR images and repositories.
6. Remove unused Lambda functions, SQS queues and CloudWatch resources.
7. Confirm that no unexpected billable resources remain.

Actual resource identifiers will be recorded during deployment.