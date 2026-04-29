# Amazon Nova 2 Sonic — 模型能力概览

> 整理时间：2026-04-29 | 来源：AWS 官方文档

## 模型简介

Amazon Nova 2 Sonic 是 AWS 的原生 **Speech-to-Speech（语音到语音）** 基础模型，通过 Amazon Bedrock 提供服务。它将语音理解和语音生成统一到单一模型中，支持低延迟、自然的实时语音对话。

### 核心参数

| 项目 | 值 |
|---|---|
| 模型名称 | Amazon Nova 2 Sonic |
| Model ID | `amazon.nova-2-sonic-v1:0` |
| 发布日期 | 2025-12-02 |
| 模型类型 | Speech-to-Speech 基础模型 |
| 输入模态 | Speech（语音） |
| 输出模态 | Speech（语音）+ Text（文本） |
| 上下文窗口 | 1M tokens |
| 最大输出 | 64K tokens |
| API | `InvokeModelWithBidirectionalStream` |
| Endpoint | `bedrock-runtime` |
| 服务层级 | Standard（按量付费） |

## 语言支持

### 支持语言与语音列表

Nova 2 Sonic 支持 **7 种语言 / 10 个语言区域**，每种语言提供至少一个女性和男性语音：

| 语言 | Locale | 女性语音 ID | 男性语音 ID |
|---|---|---|---|
| 英语（美国） | en-US | tiffany | matthew |
| 英语（英国） | en-GB | amy | - |
| 英语（澳大利亚） | en-AU | olivia | - |
| 英语（印度） | en-IN | kiara | arjun |
| 法语 | fr-FR | ambre | florian |
| 意大利语 | it-IT | beatrice | lorenzo |
| 德语 | de-DE | tina | lennart |
| 西班牙语（美国） | es-US | lupe | carlos |
| 葡萄牙语（巴西） | pt-BR | carolina | leo |
| 印地语 | hi-IN | kiara | arjun |

### 多语言能力

- **Tiffany**（en-US 女声）和 **Matthew**（en-US 男声）是**唯一支持所有语言的多语言语音**
- 支持 **Code-Switching**（同一句话中混合多种语言）
- 支持**语言镜像**（自动识别用户语言并以相同语言回复）

### ⚠️ 中文支持情况

**目前 Nova 2 Sonic 不支持中文（普通话/粤语）**。支持的语言限于上述 7 种。如需中文语音交互，建议：
1. 使用中文 ASR（如 Amazon Transcribe）转文字 → Nova 文本模型处理 → TTS 输出
2. 等待后续版本更新

## 能力边界

### ✅ 支持的能力

| 能力 | 说明 |
|---|---|
| 实时语音对话 | 双向流式通信，低延迟 |
| 语音识别（ASR） | 内置语音转文字，支持输出转写文本 |
| 语音合成（TTS） | 多语言、多语音自然合成 |
| 多语言对话 | 7 种语言，支持语言切换 |
| System Prompt | 控制助手行为、人设、回复风格 |
| Speech Prompt | 控制印地语转写格式（Latin/Devanagari） |
| Tool Use | 支持外部工具调用（Function Calling） |
| 语音活动检测（VAD） | 内置端点检测，自动识别用户说话结束 |
| 性别一致性 | 语音性别与语法性别一致（对有语法性别的语言） |
| 推理能力 | 支持 Chain-of-Thought 推理模式 |
| Response Streaming | 流式响应输出 |

### ❌ 不支持 / 受限

| 限制 | 说明 |
|---|---|
| 中文 | 不在当前支持语言列表中 |
| 日语/韩语 | 不在当前支持语言列表中 |
| 连接时长 | **单次连接最长 8 分钟**，需 session continuation 模式 |
| Guardrails | 不支持 Bedrock Guardrails |
| Knowledge Base | 不支持直接关联 Bedrock Knowledge Base |
| Agents | 不支持 Bedrock Agents 集成 |
| Prompt Routing | 不支持智能提示路由 |
| 跨区推理 | 仅支持 In-Region，不支持 Geo/Global 路由 |
| 音频理解 | 仅处理语音，不理解背景音乐/环境声 |
| 视频 | 不支持视频输入输出 |
| 图像 | 不支持图像输入输出 |

### 可用 Region

| Region | 代码 |
|---|---|
| 弗吉尼亚北部 | `us-east-1` |
| 俄勒冈 | `us-west-2` |
| 斯德哥尔摩 | `eu-north-1` |
| 东京 | `ap-northeast-1` |

## 事件流协议

Nova 2 Sonic 使用双向流式事件协议，核心事件序列：

```
Session Start → Prompt Start → System Prompt → Audio Input → ... → Prompt End → Session End
```

### 事件类型

| 事件 | 方向 | 说明 |
|---|---|---|
| `sessionStart` | → 模型 | 初始化会话，设置推理参数 |
| `promptStart` | → 模型 | 开始提示，配置音频输出（语音、采样率） |
| `contentStart` | → 模型 | 开始内容块（TEXT/AUDIO，SYSTEM/USER 角色） |
| `textInput` | → 模型 | 发送文本内容（System Prompt） |
| `audioInput` | → 模型 | 发送音频数据（base64 编码） |
| `contentEnd` | → 模型 | 结束内容块 |
| `promptEnd` | → 模型 | 结束提示 |
| `sessionEnd` | → 模型 | 结束会话 |
| `textOutput` | ← 模型 | 接收文本输出（ASR 转写 / 助手回复） |
| `audioOutput` | ← 模型 | 接收音频输出（base64 编码） |
| `contentStart` | ← 模型 | 模型开始输出内容 |
| `contentEnd` | ← 模型 | 模型结束输出内容 |

## 音频格式

| 参数 | 输入 | 输出 |
|---|---|---|
| 格式 | `audio/lpcm` | `audio/lpcm` |
| 采样率 | 16000 Hz | 24000 Hz |
| 位深 | 16-bit | 16-bit |
| 声道 | 单声道（Mono） | 单声道（Mono） |
| 编码 | base64 | base64 |

## 集成方式

Nova 2 Sonic 支持通过 **Amazon Bedrock AgentCore** 部署，提供：
- 托管运行时环境
- 企业级安全和可扩展性
- 自动处理基础设施、认证和 WebSocket 连接

## 参考链接

- [Nova 2 Sonic Model Card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-2-sonic.html)
- [Getting Started](https://docs.aws.amazon.com/nova/latest/nova2-userguide/sonic-getting-started.html)
- [Language Support](https://docs.aws.amazon.com/nova/latest/nova2-userguide/sonic-language-support.html)
- [Voice Conversation Prompts](https://docs.aws.amazon.com/nova/latest/nova2-userguide/sonic-system-prompts.html)
- [Nova Samples GitHub](https://github.com/aws-samples/amazon-nova-samples)
- [Amazon Bedrock Pricing](https://aws.amazon.com/bedrock/pricing/)
