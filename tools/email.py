from agentmail import AgentMail
from langchain_core.tools import tool
from pydantic import BaseModel, Field


def init_send_email_tool(inbox_id: str, api_key: str):
    client = AgentMail(api_key=api_key)

    class SendEmailInput(BaseModel):
        to: str | list[str] = Field(description="Recipient address(es)")
        subject: str = Field(default="", description="Email subject")
        text: str = Field(default="", description="Plain text body")
        html: str = Field(default="", description="HTML body")
        reply_to_message_id: str = Field(default="", description="Message ID to reply to (for threading)")

    @tool("send_email", args_schema=SendEmailInput)
    def send_email(to: str | list[str], subject: str = "", text: str = "", html: str = "", reply_to_message_id: str = "") -> dict:
        """Send an email from the assigned inbox. Set reply_to_message_id to reply within a thread."""
        headers = {}
        if reply_to_message_id:
            headers["In-Reply-To"] = reply_to_message_id
            headers["References"] = reply_to_message_id
        resp = client.inboxes.messages.send(
            inbox_id=inbox_id,
            to=to, subject=subject, text=text, html=html,
            **({"headers": headers} if headers else {}),
        )
        return {"message_id": resp.message_id, "thread_id": resp.thread_id}

    return send_email
