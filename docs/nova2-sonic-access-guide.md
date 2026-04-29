# Amazon Nova 2 Sonic — 开通权限指南

## Amazon 第一方模型 — 无需 Marketplace 订阅

Nova 2 Sonic 是 Amazon 自有模型，**不需要通过 AWS Marketplace 订阅**（区别于 Anthropic、Cohere 等第三方模型）。只要 IAM 权限配置正确，可直接调用。

## 步骤一：配置 IAM 权限

确保调用角色/用户拥有以下权限：

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowNova2SonicAccess",
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
        "bedrock:InvokeModelWithBidirectionalStream"
      ],
      "Resource": "arn:aws:bedrock:*::foundation-model/amazon.nova-2-sonic-v1:0"
    }
  ]
}
```

> ⚠️ **关键点**：Nova 2 Sonic 使用 `InvokeModelWithBidirectionalStream` API（双向流式），务必确保该 Action 已授权。

如果需要更宽泛的 Bedrock 访问，也可直接附加 AWS 托管策略：`AmazonBedrockFullAccess`

## 步骤二：选择可用 Region

Nova 2 Sonic **仅支持 In-Region 推理**（不支持跨区路由）：

| Region | Region Code |
|---|---|
| 弗吉尼亚北部 | `us-east-1` |
| 俄勒冈 | `us-west-2` |
| 斯德哥尔摩 | `eu-north-1` |
| 东京 | `ap-northeast-1` |

## 步骤三：安装 SDK

```bash
pip install aws-sdk-bedrock-runtime boto3
```

## 步骤四：配置凭证

```bash
# 方式一：环境变量
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_DEFAULT_REGION="us-east-1"

# 方式二：AWS CLI 配置
aws configure
```

## 步骤五：控制台验证

1. 打开 [Amazon Bedrock Console](https://console.aws.amazon.com/bedrock/)
2. 左侧导航 → **Playgrounds** → **Chat / Text**
3. 选择 **Amazon** → **Nova 2 Sonic**
4. 如果能看到并选择该模型，说明权限已就绪

## 常见问题

### AccessDeniedException

1. 检查 IAM 是否包含 `bedrock:InvokeModelWithBidirectionalStream` 权限
2. 检查组织 SCP 是否限制了 Bedrock 访问
3. 确认在支持的 4 个 Region 之一操作
4. 确认账户有有效付款方式

### 与第三方模型的区别

| 对比项 | Nova 2 Sonic（Amazon 模型） | 第三方模型（如 Anthropic） |
|---|---|---|
| Marketplace 订阅 | 不需要 | 需要 `aws-marketplace:Subscribe` |
| 首次使用表单 | 不需要 | Anthropic 需要 FTU 表单 |
| 权限控制 | 仅需 Bedrock IAM Action | 需要 Bedrock + Marketplace 权限 |
