from dotenv import dotenv_values

env = dotenv_values(".env")

class Config:
    api_key = env['api_key']
    secret_key = env['secret_key']
    redis_url = env['redis']
