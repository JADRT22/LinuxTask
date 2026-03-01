from drivers.gnome import GnomeDriver

def test_clamping():
    driver = GnomeDriver()
    print(f"Testing clamping for resolution: {driver.screen_width}x{driver.screen_height}")
    
    # Test top-left corner (should be 0,0)
    driver.virtual_x, driver.virtual_y = 10, 10
    driver.sync_delta(-20, -20)
    print(f"Target: (0,0) | Actual: {driver.get_cursor_pos()}")
    
    # Test bottom-right corner (should be width-1, height-1)
    driver.virtual_x, driver.virtual_y = driver.screen_width - 10, driver.screen_height - 10
    driver.sync_delta(50, 50)
    print(f"Target: ({driver.screen_width-1}, {driver.screen_height-1}) | Actual: {driver.get_cursor_pos()}")
    
    # Test middle screen
    driver.virtual_x, driver.virtual_y = 500, 500
    driver.sync_delta(100, -50)
    print(f"Target: (600, 450) | Actual: {driver.get_cursor_pos()}")

    if driver.get_cursor_pos() == (600, 450):
        print("\nSUCCESS: Coordinate clamping and sync working perfectly!")
        return True
    return False

if __name__ == "__main__":
    test_clamping()
