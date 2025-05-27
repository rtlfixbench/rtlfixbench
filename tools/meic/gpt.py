import re
import time
import random
import requests

MAX_RETRIES = 10
MAX_TOKENS = 4096
TEMPERATURE = 0.7
BACKOFF_FECTOR = 10

def create_session(config):
    session = requests.Session()
    session.headers.update({
        'Authorization': f'Bearer {config["key"]}',
        'Content-Type': 'application/json'
    })
    return session

def post(config, session, history, content, system, retries=MAX_RETRIES, backoff_factor=BACKOFF_FECTOR):
    for i in range(retries):
        try:
            role = 'system' if system else 'user'
            msg = {'role': role, 'content': content}
            if system:
                history.append(msg)
            else:
                response = session.post(
                    config['url'],
                    json={
                        'model': config['model'],
                        'messages': history + [msg],
                        'temperature': config.get('temperature', TEMPERATURE),
                        'max_tokens': config.get('max_tokens', MAX_TOKENS)
                    }
                )
                response.raise_for_status()
                resp = response.json()
                if 'choices' in resp:
                    choice = resp['choices'][0]
                    if 'message' in choice and 'content' in choice['message']:
                        return choice['message']['content']
        except requests.exceptions.HTTPError as http_err:
            if http_err.response.status_code == 429:
                total = backoff_factor * (2 ** i)
                sleep_time = random.randint(total / 2, total)
                time.sleep(sleep_time)
            print(f'HTTP error occurred: {http_err}')
        except Exception as err:
            print(f'Other error occurred: {err}')
    return {}

class ScoreGPT:    
    def __init__(self, config):
        self.history = []
        self.config = config
        self.session = create_session(config)

    def get_score(self, results):
        pattern = r"\d+"
        score_items = re.findall(pattern, results)
        score = list(map(int, score_items))
        return score

    def request(self, spec, original_code, modified_code):
        content = """You are an expert in HDL design, especially skilled in verilog code writing, correction and explanation.
The user will provide you with a designed Spec (design description), as well as an original code and a modified code.
Please rate these two codes according to syntax and functionality, ranging from 0 to 100.
Only the total score of the two is given, no introduction is needed.
Answer in the following format:
original code: (total score)
modified code: (total score)"""
        start_time = time.time()
        post(self.config, self.session, self.history, content, True)
        content = f"The Spec (design description) is\n\n{spec}\n\nThe original code is\n\n{original_code}\n\nThe modified code is\n\n{modified_code}"
        results = post(self.config, self.session, self.history, content, False)
        end_time = time.time()
        score = self.get_score(results)
        return int(score[0]), int(score[1]), end_time - start_time

class DebugGPT:
    def __init__(self, config):
        self.history = []
        self.config = config
        self.session = create_session(config)

    def get_code(self, results):
        pattern = r"```verilog(.*?)```"
        matches = re.findall(pattern, results, re.DOTALL | re.IGNORECASE)
        code = ""
        for match in matches:
            code += match
        return code

    def request(self, spec, design, report_type, report_content):
        start_time = time.time()
        content = (
            f"The design description is\n\n{spec}\n\n"
            f"The design code is\n\n{design}\n\n"
            f"The debugging report is\n\n{report_content}\n\n"
            f"Please fix the error according to the {report_type.lower()} report."
            "\nOffer just corrected Verilog design code without testbench, no explanation."
        )
        results = post(self.config, self.session, self.history, content, False)
        end_time = time.time()
        code = self.get_code(results)
        return code, end_time - start_time
