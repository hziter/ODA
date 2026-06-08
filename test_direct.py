"""用 Flask test client 测试"""
import sys
sys.path.insert(0, r'C:\Users\HZ\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\work-mode-projects\6a2606e0a08f0c4691d79e6e\opendisksize')

try:
    import importlib
    # 强制重新加载
    if 'app' in sys.modules:
        del sys.modules['app']
    import app as app_module
    
    test_client = app_module.app.test_client()
    test_client.application.config['TESTING'] = True
    test_client.application.config['DEBUG'] = True
    test_client.application.config['PROPAGATE_EXCEPTIONS'] = True
    
    path = r'C:\Users\HZ\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\work-mode-projects\6a2606e0a08f0c4691d79e6e\opendisksize'
    
    print('Testing GET /api/viz/pie-ext')
    resp = test_client.get('/api/viz/pie-ext?path=' + path.replace('\\', '\\\\'))
    print('Status: {}'.format(resp.status_code))
    
    if resp.status_code != 200:
        # 手动调用函数获取详细异常
        try:
            with app_module.app.test_request_context('/api/viz/pie-ext?path=' + path):
                app_module.get_pie_by_extension()
        except Exception as e:
            import traceback
            print('Exception: {}'.format(e))
            print(traceback.format_exc())
    else:
        print('Data: {}'.format(resp.get_json()[:200] if hasattr(resp.get_json(), '__getitem__') else resp.data[:300]))

except Exception as e:
    import traceback
    print('Import error: {}'.format(e))
    print(traceback.format_exc())
