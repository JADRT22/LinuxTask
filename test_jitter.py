import random
import unittest

# Mocking the jitter logic from the main app for isolated testing
def apply_jitter(x, y, enabled=True):
    if not enabled:
        return x, y
    
    # Logic copied from main.py
    new_x = x + random.randint(-2, 2)
    new_y = y + random.randint(-2, 2)
    return new_x, new_y

class TestMacroJitter(unittest.TestCase):
    def test_jitter_bounds(self):
        """Verify that jitter does not deviate more than +-2px"""
        original_x, original_y = 100, 100
        
        for _ in range(100): # Test 100 times
            jx, jy = apply_jitter(original_x, original_y, enabled=True)
            
            delta_x = abs(jx - original_x)
            delta_y = abs(jy - original_y)
            
            self.assertLessEqual(delta_x, 2, f"X deviation too high: {delta_x}")
            self.assertLessEqual(delta_y, 2, f"Y deviation too high: {delta_y}")

    def test_jitter_disabled(self):
        """Verify that jitter does nothing when disabled"""
        x, y = apply_jitter(500, 500, enabled=False)
        self.assertEqual(x, 500)
        self.assertEqual(y, 500)

if __name__ == '__main__':
    unittest.main()
