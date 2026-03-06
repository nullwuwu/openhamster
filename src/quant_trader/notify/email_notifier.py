"""
邮件通知器
"""
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional

from .base_notifier import BaseNotifier

logger = logging.getLogger("quant_trader.notify.email")


class EmailNotifier(BaseNotifier):
    """邮件通知器"""
    
    name = "email"
    
    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        sender: str,
        password: str,
        receivers: List[str],
        use_ssl: bool = True,
    ):
        """
        初始化
        
        Args:
            smtp_host: SMTP 服务器地址
            smtp_port: SMTP 端口 (465 for SSL, 587 for TLS)
            sender: 发件人邮箱
            password: 授权码或密码
            receivers: 收件人列表
            use_ssl: 是否使用 SSL (默认 True)
        """
        super().__init__()
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.sender = sender
        self.password = password
        self.receivers = receivers
        self.use_ssl = use_ssl
    
    def send(self, title: str, body: str) -> bool:
        """
        发送邮件
        
        Args:
            title: 标题
            body: 内容 (HTML)
            
        Returns:
            bool: 是否成功
        """
        try:
            # 创建邮件
            msg = MIMEMultipart("alternative")
            msg["Subject"] = title
            msg["From"] = self.sender
            msg["To"] = ", ".join(self.receivers)
            
            # 添加 HTML 内容
            html_part = MIMEText(body, "html", "utf-8")
            msg.attach(html_part)
            
            # 连接 SMTP 服务器并发送
            if self.use_ssl:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=10)
            else:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10)
                server.starttls()
            
            server.login(self.sender, self.password)
            server.sendmail(self.sender, self.receivers, msg.as_string())
            server.quit()
            
            logger.info(f"✅ 邮件发送成功: {title}")
            return True
            
        except smtplib.SMTPException as e:
            logger.error(f"❌ 邮件发送失败: {e}")
            return False
        
        except Exception as e:
            logger.error(f"❌ 邮件发送异常: {e}")
            return False
