

from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
import webbrowser
import os
import mysql.connector
from mysql.connector import Error
from db_config import DB_CONFIG


app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# 各クライアントが参加している部屋を追跡: {sid: room_name}
client_rooms = {}

# --- MySQL接続ユーティリティ ---
def get_db_connection():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        print(f"DB接続エラー: {e}")
        return None

class ProjectDB:
    @staticmethod
    def save(name, objects_dict):
        conn = get_db_connection()
        if not conn:
            return False
        try:
            cur = conn.cursor()
            cur.execute("REPLACE INTO projects (name, data) VALUES (%s, %s)", (name, json.dumps(objects_dict, ensure_ascii=False)))
            conn.commit()
            cur.close()
            return True
        except Exception as e:
            print(f"保存失敗: {e}")
            return False
        finally:
            conn.close()

    @staticmethod
    def load(name):
        conn = get_db_connection()
        if not conn:
            return None
        try:
            cur = conn.cursor()
            cur.execute("SELECT data FROM projects WHERE name=%s", (name,))
            row = cur.fetchone()
            cur.close()
            if row:
                return json.loads(row[0])
            return None
        except Exception as e:
            print(f"読込失敗: {e}")
            return None
        finally:
            conn.close()

    @staticmethod
    def list_names():
        conn = get_db_connection()
        if not conn:
            return []
        try:
            cur = conn.cursor()
            cur.execute("SELECT name FROM projects")
            names = [row[0] for row in cur.fetchall()]
            cur.close()
            return names
        except Exception as e:
            print(f"一覧取得失敗: {e}")
            return []
        finally:
            conn.close()

import json

# ルーム単位でのオブジェクト管理: {room_name: {object_id: obj}}
room_objects = {}
# ルーム単位でのオブジェクトIDカウンター: {room_name: counter}
room_id_counter = {}
# ルーム単位での選択状態管理: {room_name: {obj_id: sid}}
room_object_selected_by = {}

def get_room_for_client(sid):
    """クライアントが参加している部屋を取得"""
    return client_rooms.get(sid)

def ensure_room_exists(room_name):
    """部屋が存在することを確認"""
    if room_name not in room_objects:
        room_objects[room_name] = {}
        room_id_counter[room_name] = 1
        room_object_selected_by[room_name] = {}

# --- 部屋への参加 ---
@socketio.on('join_room')
def handle_join_room(data):
    room_name = data.get('room_name')
    if not room_name:
        emit('error', {'message': 'room_name required'})
        return
    
    sid = request.sid
    
    # 既に別の部屋に参加していたら、そこから退出
    if sid in client_rooms:
        old_room = client_rooms[sid]
        leave_room(old_room)
        # 選択状態をクリア
        if old_room in room_object_selected_by:
            to_remove = [oid for oid, s in room_object_selected_by[old_room].items() if s == sid]
            for oid in to_remove:
                del room_object_selected_by[old_room][oid]
                emit('object_deselected', {'id': oid}, room=old_room)
    
    # 新しい部屋に参加
    client_rooms[sid] = room_name
    join_room(room_name)
    ensure_room_exists(room_name)
    
    # クライアントに現在の部屋のオブジェクト情報を送信
    emit('init_objects', list(room_objects[room_name].values()))

# --- オブジェクト削除イベント ---
@socketio.on('delete_object')
def handle_delete_object(data):
    room = get_room_for_client(request.sid)
    if not room:
        return
    
    obj_id = data['id']
    if obj_id in room_objects[room]:
        del room_objects[room][obj_id]
        # 選択状態も解除
        if obj_id in room_object_selected_by[room]:
            del room_object_selected_by[room][obj_id]
        emit('object_deleted', {'id': obj_id}, room=room)

# --- 面編集イベント ---
@socketio.on('edit_face')
def handle_edit_face(data):
    room = get_room_for_client(request.sid)
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
    }, room=room, broadcast=True, include_self=False)

# --- オブジェクト選択 ---
@socketio.on('select_object')
def handle_select_object(data):
    room = get_room_for_client(request.sid)
    if not room:
        return
    
    obj_id = data['id']
    sid = request.sid
    
    # すでに他ユーザーが選択していないかチェック
    if obj_id in room_object_selected_by[room] and room_object_selected_by[room][obj_id] != sid:
        emit('select_result', {'id': obj_id, 'result': False})
        return
    
    room_object_selected_by[room][obj_id] = sid
    emit('object_selected', {'id': obj_id, 'sid': sid}, room=room)
    emit('select_result', {'id': obj_id, 'result': True})

# --- オブジェクト選択解除 ---
@socketio.on('deselect_object')
def handle_deselect_object(data):
    room = get_room_for_client(request.sid)
    if not room:
        return
    
    obj_id = data['id']
    sid = request.sid
    
    if obj_id in room_object_selected_by[room] and room_object_selected_by[room][obj_id] == sid:
        del room_object_selected_by[room][obj_id]
        emit('object_deselected', {'id': obj_id}, room=room)

# --- 切断処理 ---
@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    room = client_rooms.get(sid)
    
    if room and room in room_object_selected_by:
        # 切断時にそのユーザーが選択していたものを解除
        to_remove = [oid for oid, s in room_object_selected_by[room].items() if s == sid]
        for oid in to_remove:
            del room_object_selected_by[room][oid]
            emit('object_deselected', {'id': oid}, room=room)
    
    if sid in client_rooms:
        del client_rooms[sid]


# --- プロジェクト保存API ---
@app.route('/api/save_project', methods=['POST'])
def api_save_project():
    data = request.get_json()
    name = data.get('name')
    objects_dict = data.get('objects')
    room = data.get('room')
    
    if not name or objects_dict is None:
        return jsonify({'success': False, 'error': 'name/objects required'}), 400
    
    # 指定された部屋が有効な部屋であるかチェック
    valid_rooms = ['a', 'b', 'c']
    if room not in valid_rooms:
        return jsonify({'success': False, 'error': 'invalid room'}), 400
    
    result = ProjectDB.save(name, objects_dict)
    return jsonify({'success': result})

# --- プロジェクト読込API（部屋の初期化用） ---
@app.route('/api/load_project', methods=['GET'])
def api_load_project():
    name = request.args.get('name')
    if not name:
        return jsonify({'success': False, 'error': 'name required'}), 400
    objects_dict = ProjectDB.load(name)
    if objects_dict is None:
        return jsonify({'success': False, 'error': 'not found'}), 404
    return jsonify({'success': True, 'objects': objects_dict})

# --- プロジェクト名一覧API ---
@app.route('/api/list_projects', methods=['GET'])
def api_list_projects():
    names = ProjectDB.list_names()
    return jsonify({'success': True, 'projects': names})

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    # 部屋参加待ち（join_roomイベント待ち）
    pass

@socketio.on('add_object')
def handle_add_object(data):
    room = get_room_for_client(request.sid)
    if not room:
        return
    
    ensure_room_exists(room)
    
    obj = {
        'id': room_id_counter[room],
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
    
    room_objects[room][room_id_counter[room]] = obj
    room_id_counter[room] += 1
    emit('add_object', obj, room=room)

# --- 移動・回転・スケール操作 ---
@socketio.on('move_object')
def handle_move_object(data):
    room = get_room_for_client(request.sid)
    if not room or room not in room_objects:
        return
    
    obj_id = data['id']
    if obj_id in room_objects[room]:
        room_objects[room][obj_id]['position'] = data['position']
        emit('move_object', {
            **room_objects[room][obj_id],
        }, room=room, broadcast=True, include_self=False)

@socketio.on('rotate_object')
def handle_rotate_object(data):
    room = get_room_for_client(request.sid)
    if not room or room not in room_objects:
        return
    
    obj_id = data['id']
    rotation = data['rotation']
    if obj_id in room_objects[room]:
        room_objects[room][obj_id]['rotation'] = rotation
        emit('rotate_object', {
            **room_objects[room][obj_id],
        }, room=room, broadcast=True, include_self=False)

@socketio.on('scale_object')
def handle_scale_object(data):
    room = get_room_for_client(request.sid)
    if not room or room not in room_objects:
        return
    
    obj_id = data['id']
    scale = data['scale']
    if obj_id in room_objects[room]:
        room_objects[room][obj_id]['scale'] = scale
        emit('scale_object', {
            **room_objects[room][obj_id],
        }, room=room, broadcast=True, include_self=False)

if __name__ == '__main__':
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        webbrowser.open('http://localhost:5000/')
    socketio.run(app, host="0.0.0.0", debug=True)