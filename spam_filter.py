import re
from typing import List, Tuple, Optional
from database import SpamDB

class SilentSpamFilter:
    def __init__(self, db: SpamDB):
        self.db = db
        self._cache = []  # Кэш паттернов для быстрой проверки
        self.reload_patterns()
    
    def reload_patterns(self):
        """Перезагрузить паттерны из БД в кэш"""
        samples = self.db.get_all_samples()
        self._cache = []
        for text, ptype in samples:
            if ptype == 'regex':
                try:
                    self._cache.append((re.compile(text, re.IGNORECASE), 'regex'))
                except re.error:
                    continue  # Некорректный regex игнорируем
            else:
                self._cache.append((text.lower(), ptype))
    
    def is_spam(self, message_text: str) -> bool:
        if not message_text:
            return False
        
        text_lower = message_text.lower()
        
        for pattern, ptype in self._cache:
            if ptype == 'exact' and pattern == text_lower:
                return True
            elif ptype == 'substring' and pattern in text_lower:
                return True
            elif ptype == 'regex' and pattern.search(message_text):
                return True
        
        # Дополнительные эвристики (без ложных срабатываний)
        # 1. Слишком много ссылок (>2 в одном сообщении)
        links = re.findall(r'https?://[^\s]+|t\.me/[^\s]+|@[a-zA-Z0-9_]{5,}', message_text)
        if len(links) >= 2:
            return True
        
        # 2. Подозрительные последовательности символов (спам-генераторы)
        if re.search(r'([a-z]{15,})', message_text.lower()):
            return True
        
        return False