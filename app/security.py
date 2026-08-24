"""
Remains between user and the LLM. 
This module is responsible for handling security-related tasks, 
such as authentication and authorization, to ensure that only a
uthorized users can access the system's resources.
"""

import re
from typing import Optional
from langsmith import traceable

class InputSanitizer:
    """
    A class to sanitize user input to prevent injection attacks.
    """

    INJECTION_PATTERN = [
        r"ignore\s+(?:all\s+)?previous\s+instructions",  # Matches "ignore all previous instructions" or "ignore previous instructions"
        r"forget\s+(?:all\s+)?previous\s+instructions",  # Matches "forget all previous instructions" or "forget previous instructions"
        r"new\s+instructions\s*:",  # Matches "new instructions:" with optional whitespace
        r"system\s*prompt\s*:",  # Matches "system prompt:" with optional whitespace
        r"---\s*end\s*(of)?\s*prompt\s*---",  # Matches "--- end of prompt ---" with optional whitespace
        r"pretend\s+you\s+are\s+.*",  # Matches "pretend you are ..." with any characters after
        r"act\s+as\s+(if\s+)?you\s+are\s+.*",  # Matches "act as if you are ..." or "act as you are ..."
        r"bypass\s+(all\s+)?restrictions",  # Matches "bypass all restrictions" or "bypass restrictions"
        r"reveal\s+(your|the)\s+(system|instructions|prompt)",  # Matches "reveal your system instructions" or "reveal the prompt"
        r"you\s+are\s+now\s+(DAN|jailbroken|unrestricted)",  # Matches "you are now DAN" or similar phrases
        r"ignore\s+the\s+rules",  # Matches "ignore the rules"
    ]

    def __init__(self):
        """
        Initialize the InputSanitizer with a list of patterns to check against.
        
        """
        self.patterns = [
            re.compile(pattern, re.IGNORECASE) 
            for pattern in self.INJECTION_PATTERN
        ]

    def check_for_injection(self, user_input: str) -> tuple[bool, Optional[str]]:
        """
        Check the user input for any patterns that indicate an injection attempt.
        
        Args:
            user_input (str): The input string from the user.

        Returns:
            tuple[bool, Optional[str]]: A tuple containing a boolean indicating if an injection was found and the detected injection pattern, or None if no injection is found.
        """
        for pattern in self.patterns:
            if pattern.search(user_input):
                return True, pattern.pattern
        return False, None
    
    def sanitize_input(self, user_input: str) -> str:
        """
        Sanitize the user input by removing potentially harmful characters.

        Args:
            user_input (str): The input string from the user.

        Returns:
            str: The sanitized input string.
        """
        
        sanitized = re.sub(r'<script.*?>.*?</script>', '', user_input, flags=re.IGNORECASE | re.DOTALL) # Remove any script tags and their content
        
        sanitized = re.sub(r'[<>]', '', sanitized)  # Remove any other potentially harmful characters

        sanitized =  re.sub(r'[-]{3,}', '', sanitized)  # Remove sequences of three or more hyphens
        sanitized =  re.sub(r'[=]{3,}', '', sanitized)  # Remove sequences of three or more equal signs

        return sanitized.strip()

class PIIDetector:
    """
    A class to detect Personally Identifiable Information (PII) in user input.
    """

    PII_PATTERNS = {
        "ssn": r"\b\d{3}-\d{2}-\d{4}\b",  # Matches SSN format: 123-45-6789
        "phone": r"\b\d{3}\s\d{2}\s\d{4}\b",  # Matches SSN format with spaces: 123 45 6789
        "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b",  # Matches email addresses
        "credit_card": r"\b(?:\d[ -]*?){13,16}\b",  # Matches credit card numbers (13 to 16 digits)
        "ip_address": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",  # Matches IPv4 addresses
    }

    MASK_MAP = {
        "ssn": "[REDACTED_SSN]",
        "phone": "[REDACTED_PHONE]",
        "email": "[REDACTED_EMAIL]",
        "credit_card": "[REDACTED_CREDIT_CARD]",
        "ip_address": "[REDACTED_IP_ADDRESS]"
    }

    def detect_pii(self, user_input: str) -> dict:
        """
        Detect PII in the user input.

        Args:
            user_input (str): The input string from the user.

        Returns:
            dict: A dictionary containing the detected PII types and their corresponding masked values.
        """
        detected_pii = {}
        for pii_type, pattern in self.PII_PATTERNS.items():
            matches = re.findall(pattern, user_input, re.IGNORECASE)
            if matches:
                detected_pii[pii_type] = [self.MASK_MAP[pii_type]] * len(matches)
        return detected_pii

    def mask_pii(self, user_input: str) -> str:
        """
        Mask PII in the user input.

        Args:
            user_input (str): The input string from the user.

        Returns:
            Masked user input
        """
        masked = user_input
        for pii_type, pattern in self.PII_PATTERNS.items():
            masked = re.sub(pattern, self.MASK_MAP[pii_type], masked)
        return masked


class OutputValidator:
    """
    Validates LLM output before returning to the client.
    Catches PII leakage and harmful content in reponses.
    """
    HARMFUL_PATTERNS  =  [
        re.compile(r"here(?:'s| is)\s+(how|the way) to\s+(hack|steal|attack)", re.I),
        re.compile(r"password\s+is\s+", re.I),
        re.compile(r"api[_\s]?key\s*[:=]", re.I)
    ]

    def  __init__(self):
        self.pii_detector = PIIDetector()

    def validate(self, output:str) -> tuple[str, list[str]]:
        """
        Validate and clean output.
        returns: (cleaned_output, list_of_warnings)
        """
        warnings  = []

        pii_found = self.pii_detector.detect_pii(output)
        if pii_found:
            output = self.pii_detector.mask_pii(output)
            warnings.append("PII redacted")

        for pattern in self.HARMFUL_PATTERNS:
            if pattern.search(output):
                output  = "[Response BLOCKED: Potentially harmful content]"
                warnings.append("Potentially harmful content detected")
                break

        return output, warnings

class SecurityPipeline:
    """
    Full security pipeline that processes ip and op.
    This is the single class you wire into API.
    """

    def __init__(self):
        self.sanitizer = InputSanitizer()
        self.pii_detector = PIIDetector()
        self.output_validator  = OutputValidator()

    @traceable(name="security_check_point")
    def check_input(self, user_input: str) -> tuple[bool, str, list[str]]:
        """
        Process input through security checks.
        Returns: (is_allowed, cleaned_text, security_notes)
        """
        notes  = []

        #Step 1 - check for injection
        injection_detected, reason = self.sanitizer.check_for_injection(user_input)

        if injection_detected:
            return False, "", [reason or "Prompt injection detected"]

        #Step 2
        sanitized  = self.sanitizer.sanitize_input(user_input)

        #step 3
        pii_found = self.pii_detector.detect_pii(sanitized)

        if pii_found:
            sanitized = self.pii_detector.mask_pii(sanitized)
            notes.append(f"Input PII masked: {list(pii_found.keys())}")

        return True, sanitized, notes

    @traceable(name="security_check_output")
    def check_output(self, user_input: str) -> tuple[str, list[str]]:
        """
        Validate output before returning to User.
        Returns:  (cleaned_output, warnings)
        """
        return self.output_validator.validate(user_input)