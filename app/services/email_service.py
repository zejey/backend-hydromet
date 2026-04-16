from app.config import Config

class EmailService:
    @staticmethod
    def send_otp_email(recipient_email: str, otp_code: str) -> dict:
        """Send OTP via Brevo (Sendinblue)"""
        try:
            if not Config.BREVO_API_KEY or not Config.BREVO_SENDER:
                raise Exception("Missing BREVO_API_KEY or BREVO_SENDER in environment")

            import sib_api_v3_sdk
            
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

    @staticmethod
    def send_hazard_alert_email(
        recipient_email: str, 
        hazard_name: str, 
        horizon: int, 
        probability: float,
        safety_tips: list = None
    ) -> dict:
        """Send Hazard Alert via Brevo"""
        try:
            if not Config.BREVO_API_KEY or not Config.BREVO_SENDER:
                raise Exception("Missing BREVO_API_KEY or BREVO_SENDER in environment")

            import sib_api_v3_sdk
            
            configuration = sib_api_v3_sdk.Configuration()
            configuration.api_key['api-key'] = Config.BREVO_API_KEY

            api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
                sib_api_v3_sdk.ApiClient(configuration)
            )

            risk_pct = int(probability * 100)
            color = "#d9534f" if risk_pct > 70 else "#f0ad4e"
            
            tips_html = ""
            if safety_tips:
                tips_html = "<div style='background: #fff; padding: 15px; border-radius: 5px; margin-top: 20px;'>"
                tips_html += "<h3 style='margin-top: 0; color: #333;'>Safety Actions:</h3><ul style='padding-left: 20px; color: #555;'>"
                for tip in safety_tips:
                    tips_html += f"<li>{tip}</li>"
                tips_html += "</ul></div>"

            html_content = f"""
            <html>
            <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding: 20px; background-color: #f4f4f4;">
                <div style="max-width: 600px; margin: 0 auto; background: white; padding: 0; border-radius: 10px; overflow: hidden; border: 1px solid #ddd;">
                    <div style="background-color: {color}; padding: 20px; text-align: center; color: white;">
                        <h1 style="margin: 0; font-size: 24px;">⚠️ HAZARD ALERT</h1>
                    </div>
                    <div style="padding: 30px;">
                        <h2 style="color: #333; margin-top: 0;">{hazard_name} Expected</h2>
                        <p style="font-size: 16px; color: #555; line-height: 1.6;">
                            Our system has detected a high probability of <strong>{hazard_name}</strong> in your area within the next <strong>{horizon} hours</strong>.
                        </p>
                        <div style="background: #fdf7f7; border-left: 5px solid {color}; padding: 15px; margin: 20px 0;">
                            <p style="margin: 0; font-size: 18px; color: #333;">
                                <strong>Risk Probability:</strong> {risk_pct}%
                            </p>
                        </div>
                        {tips_html}
                        <p style="font-size: 14px; color: #888; margin-top: 30px; text-align: center;">
                            This is an automated alert from HydroMet. Please stay tuned to local news and follow official guidance.
                        </p>
                    </div>
                    <div style="background: #eee; padding: 15px; text-align: center; font-size: 12px; color: #999;">
                        &copy; 2024 HydroMet Disaster Management System
                    </div>
                </div>
            </body>
            </html>
            """

            send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
                to=[{"email": recipient_email}],
                sender={"name": "HydroMet", "email": Config.BREVO_SENDER},
                subject=f"⚠️ URGENT: {hazard_name} Alert - HydroMet",
                html_content=html_content
            )

            api_response = api_instance.send_transac_email(send_smtp_email)
            print(f"✅ Alert email sent to {recipient_email}. ID: {api_response.message_id}")
            
            return {"success": True, "message_id": api_response.message_id}
            
        except Exception as e:
            print(f"⚠️ Email service alert error: {e}")
            return {"success": False, "error": str(e)}
