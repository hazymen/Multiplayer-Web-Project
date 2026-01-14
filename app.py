
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import webbrowser
import os

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# 部屋ごとのオブジェクト管理
room_objects = {
    1: {},
    2: {},
    3: {}
}

# 部屋ごとのオブジェクトIDカウンター
room_object_id_counter = {
    1: 1,
    2: 1,
    3: 1
}

# 部屋ごとの選択状態管理
room_object_selected_by = {
    1: {}, 
    2: {},
    3: {}
}

# ユーザーが入室している部屋を管理
user_room = {}

# グローバルオブジェクト管理（互換性のため保持）
objects = {}
object_id_counter = 1
object_selected_by = {}

# オブジェクト削除イベント
@socketio.on('delete_object')
def handle_delete_object(data):
    room = user_room.get(request.sid)
    if not room:
        return
    
    obj_id = data['id']
    objects_dict = room_objects[room]
    selected_dict = room_object_selected_by[room]
    
    if obj_id in objects_dict:
        del objects_dict[obj_id]
        # 選択状態も解除
        if obj_id in selected_dict:
            del selected_dict[obj_id]
        emit('object_deleted', {'id': obj_id}, to=f'room_{room}')


@socketio.on('edit_face')
def handle_edit_face(data):
    room = user_room.get(request.sid)
    if not room:
        return
    
    obj_id = data['id']
    indices = data.get('face_indices')
    delta = data.get('delta')
    emit('edit_face', {
        'id': obj_id,
        'face_indices': indices,
        'delta': delta,
        'childMeshIndex': data.get('childMeshIndex')
    }, to=f'room_{room}', include_self=False)

# オブジェクト情報を管理（id, type, position など）
@socketio.on('select_object')
def handle_select_object(data):
    room = user_room.get(request.sid)
    if not room:
        return
    
    obj_id = data['id']
    sid = request.sid
    selected_dict = room_object_selected_by[room]
    
    # すでに他ユーザーが選択していないかチェック
    if obj_id in selected_dict and selected_dict[obj_id] != sid:
        emit('select_result', {'id': obj_id, 'result': False})
        return
    selected_dict[obj_id] = sid
    emit('object_selected', {'id': obj_id, 'sid': sid}, to=f'room_{room}')
    emit('select_result', {'id': obj_id, 'result': True})

@socketio.on('deselect_object')
def handle_deselect_object(data):
    room = user_room.get(request.sid)
    if not room:
        return
    
    obj_id = data['id']
    sid = request.sid
    selected_dict = room_object_selected_by[room]
    
    if obj_id in selected_dict and selected_dict[obj_id] == sid:
        del selected_dict[obj_id]
        emit('object_deselected', {'id': obj_id}, to=f'room_{room}')
@socketio.on('disconnect')
def handle_disconnect():
    room = user_room.get(request.sid)
    if room:
        # 切断時にそのユーザーが選択していたものを解除
        selected_dict = room_object_selected_by[room]
        to_remove = [oid for oid, s in selected_dict.items() if s == request.sid]
        for oid in to_remove:
            del selected_dict[oid]
            emit('object_deselected', {'id': oid}, to=f'room_{room}')
        
        # ユーザーを部屋から削除
        del user_room[request.sid]
        
        # ユーザー数を通知
        broadcast_room_users()

@app.route('/')
def lobby():
    return render_template('lobby.html')

@app.route('/room/<int:room_number>')
def editor(room_number):
    if room_number not in [1, 2, 3]:
        return 'Invalid room number', 400
    return render_template('index.html')

@socketio.on('join_room')
def handle_join_room(data):
    room = data.get('room')
    if room not in [1, 2, 3]:
        return {'success': False, 'error': 'Invalid room number'}
    
    user_room[request.sid] = room
    join_room(f'room_{room}')
    
    # 現在の全オブジェクト情報を新規クライアントに送信
    objects_list = list(room_objects[room].values())
    emit('init_objects', objects_list)
    
    # ユーザー数を通知
    broadcast_room_users()
    
    return {'success': True}

@socketio.on('connect')
def handle_connect():
    # ロビー画面表示時はここで特に処理不要
    pass

@socketio.on('get_room_users')
def handle_get_room_users():
    # 各部屋のユーザー数を計算
    room_users = {
        'room1': len([sid for sid, r in user_room.items() if r == 1]),
        'room2': len([sid for sid, r in user_room.items() if r == 2]),
        'room3': len([sid for sid, r in user_room.items() if r == 3])
    }
    emit('room_users', room_users)

def broadcast_room_users():
    """すべての接続クライアントに部屋のユーザー数を通知"""
    room_users = {
        'room1': len([sid for sid, r in user_room.items() if r == 1]),
        'room2': len([sid for sid, r in user_room.items() if r == 2]),
        'room3': len([sid for sid, r in user_room.items() if r == 3])
    }
    socketio.emit('room_users', room_users, to=None)

@socketio.on('add_object')
def handle_add_object(data):
    room = user_room.get(request.sid)
    if not room:
        return
    
    global object_id_counter
    counter = room_object_id_counter[room]
    
    obj = {
        'id': counter,
        'type': data['type'],
        'position': data['position'],
    }
    # GLBモデルの場合はmodelName, rotation, scaleも保存
    if data['type'] == 'glb':
        obj['modelName'] = data.get('modelName')
        if 'rotation' in data:
            obj['rotation'] = data['rotation']
        if 'scale' in data:
            obj['scale'] = data['scale']
    else:
        obj['color'] = data.get('color', None)
        if 'rotation' in data:
            obj['rotation'] = data['rotation']
        if 'scale' in data:
            obj['scale'] = data['scale']
    
    room_objects[room][counter] = obj
    room_object_id_counter[room] = counter + 1
    object_id_counter = max(object_id_counter, counter + 1)
    
    emit('add_object', obj, to=f'room_{room}')


# --- 追加: 回転・スケール・全体同期イベント ---
@socketio.on('move_object')
def handle_move_object(data):
    room = user_room.get(request.sid)
    if not room:
        return
    
    obj_id = data['id']
    objects_dict = room_objects[room]
    
    if obj_id in objects_dict:
        objects_dict[obj_id]['position'] = data['position']
        # 既存のrotation/scaleも送る
        emit('move_object', {
            **objects_dict[obj_id],
        }, to=f'room_{room}', include_self=False)

@socketio.on('rotate_object')
def handle_rotate_object(data):
    room = user_room.get(request.sid)
    if not room:
        return
    
    obj_id = data['id']
    rotation = data['rotation']
    objects_dict = room_objects[room]
    
    if obj_id in objects_dict:
        objects_dict[obj_id]['rotation'] = rotation
        emit('rotate_object', {
            **objects_dict[obj_id],
        }, to=f'room_{room}', include_self=False)

@socketio.on('scale_object')
def handle_scale_object(data):
    room = user_room.get(request.sid)
    if not room:
        return
    
    obj_id = data['id']
    scale = data['scale']
    objects_dict = room_objects[room]
    
    if obj_id in objects_dict:
        objects_dict[obj_id]['scale'] = scale
        emit('scale_object', {
            **objects_dict[obj_id],
        }, to=f'room_{room}', include_self=False)

if __name__ == '__main__':
    # ブラウザを自動で開く
    import threading
    def open_browser():
        import time
        time.sleep(1)  # サーバー起動を待つ
        webbrowser.open('http://localhost:5000/')
    
    thread = threading.Thread(target=open_browser, daemon=True)
    thread.start()
    
    socketio.run(app, host="0.0.0.0", debug=False)