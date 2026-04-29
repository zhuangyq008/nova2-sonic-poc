# Amazon Nova 2 Sonic POC

Amazon Nova 2 Sonic 语音对话模型 POC 测试项目

## 项目结构

```
├── README.md                          # 本文件
├── docs/
│   ├── nova2-sonic-overview.md        # 模型能力概览 & 语言支持
│   ├── nova2-sonic-access-guide.md    # 开通权限指南
│   └── nova2-sonic-prompt-engineering.md  # 提示词工程指南
├── examples/
│   ├── requirements.txt               # Python 依赖
│   ├── simple_text_test.py            # 文本输入测试（无需麦克风）
│   ├── file_audio_test.py             # 音频文件输入测试
│   ├── realtime_conversation.py       # 实时麦克风对话（完整示例）
│   └── generate_test_audio.py         # 生成测试音频文件
└── audio/                             # 测试音频文件目录
```

## 快速开始

```bash
# 1. 安装依赖
cd examples
pip install -r requirements.txt

# 2. 配置 AWS 凭证
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_DEFAULT_REGION="us-east-1"

# 3. 生成测试音频
python generate_test_audio.py

# 4. 运行文本测试（无需麦克风，最简单的验证方式）
python simple_text_test.py

# 5. 运行音频文件测试
python file_audio_test.py

# 6. 实时对话测试（需要麦克风和扬声器）
python realtime_conversation.py
```

## 文档

- [Nova 2 Sonic 能力概览](docs/nova2-sonic-overview.md) — 模型介绍、语言支持、能力边界
- [开通权限指南](docs/nova2-sonic-access-guide.md) — IAM 配置、Region 选择
- [提示词工程指南](docs/nova2-sonic-prompt-engineering.md) — System Prompt 最佳实践

## 注意事项

- Nova 2 Sonic 使用 `InvokeModelWithBidirectionalStream` API（双向流式）
- 连接限制 8 分钟，需要 session continuation 模式处理长对话
- 目前仅支持 4 个 Region：us-east-1, us-west-2, eu-north-1, ap-northeast-1
- 需要安装 `aws-sdk-bedrock-runtime` Python SDK
