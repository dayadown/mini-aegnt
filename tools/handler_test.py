import os
import unittest
from handler import *

class MyTestCase(unittest.TestCase):
    def test_tool_bash(self):
        os.environ['BAIDU_API_KEY']=''
        bash_str='python ./skills/baidu-search/scripts/search.py "{\\\"query\\\":\\\"人工智能\\\"}"'
        result=tool_bash(bash_str)
        self.assertIsNotNone(result)


if __name__ == '__main__':
    unittest.main()
