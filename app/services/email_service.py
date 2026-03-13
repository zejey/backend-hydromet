from app.config import Config

class EmailService:
    @staticmethod
    def send_otp_email(recipient_email: str, otp_code: str) -> dict:
        """Send OTP via Brevo (Sendinblue)"""
        try:
            if not Config.BREVO_API_KEY or not Config.BREVO_SENDER:
                raise Exception("Missing BREVO_API_KEY or BREVO_SENDER in environment")

            import sib_api_v3_sdk
            from sib_api_v3_sdk.rest import ApiException

            configuration = sib_api_v3_sdk.Configuration()
            configuration.api_key['api-key'] = Config.BREVO_API_KEY

            api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
                sib_api_v3_sdk.ApiClient(configuration)
            )

            html_content = f"""
            <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <div style="max-width: 600px; margin: 0 auto; background: #f9f9f9; padding: 30px; border-radius: 10px;">
                    <h2 style="color: #2d5f3f; text-align: center;">HydroMet Verification Code</h2>
                    <p style="font-size: 16px; color: #333;">Your verification code is:</p>
                    <div style="background: white; padding: 20px; text-align: center; border-radius: 8px; margin: 20px 0;">
                        <h1 style="color: #2d5f3f; font-size: 36px; letter-spacing: 8px; margin: 0;">{otp_code}</h1>
                    </div>
                    <p style="font-size: 14px; color: #666;">
                        This code will expire in <strong>10 minutes</strong>.<br>
                        Do not share this code with anyone.
                    </p>
                </div>
            </body>
            </html>
            """

            send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
                to=[{"email": recipient_email}],
                sender={"name": "HydroMet", "email": Config.BREVO_SENDER},
                subject="Your HydroMet Verification Code",
                html_content=html_content
            )

            api_response = api_instance.send_transac_email(send_smtp_email)
            print(f"✅ Email sent to {recipient_email}. Message ID: {api_response.message_id}")
            
            return {"success": True, "response": api_response}
            
        except Exception as e:
            print(f"⚠️ Email service error: {e}")
            return {"success": False, "response": str(e)}
