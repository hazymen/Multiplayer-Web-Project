

from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import webbrowser
import os
import mysql.connector
from mysql.connector import Error
from db_config import DB_CONFIG


app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

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

# オブジェクト削除イベント
@socketio.on('delete_object')
def handle_delete_object(data):
    obj_id = data['id']
    if obj_id in objects:
        del objects[obj_id]
        # 選択状態も解除
        if obj_id in object_selected_by:
            del object_selected_by[obj_id]
        emit('object_deleted', {'id': obj_id}, broadcast=True)


@socketio.on('edit_face')
def handle_edit_face(data):
    obj_id = data['id']
    indices = data.get('face_indices')
    delta = data.get('delta')
    emit('edit_face', {
        'id': obj_id,
        'face_indices': indices,
        'delta': delta,
        'childMeshIndex': data.get('childMeshIndex')
    }, broadcast=True, include_self=False)
    
# オブジェクト情報を管理（id, type, position など）

objects = {}
object_id_counter = 1
# 選択状態の管理: {オブジェクトid: 選択ユーザーのsid}
object_selected_by = {}
from flask import request
@socketio.on('select_object')
def handle_select_object(data):
    obj_id = data['id']
    sid = request.sid
    # すでに他ユーザーが選択していないかチェック
    if obj_id in object_selected_by and object_selected_by[obj_id] != sid:
        emit('select_result', {'id': obj_id, 'result': False})
        return
    object_selected_by[obj_id] = sid
    emit('object_selected', {'id': obj_id, 'sid': sid}, broadcast=True)
    emit('select_result', {'id': obj_id, 'result': True})

@socketio.on('deselect_object')
def handle_deselect_object(data):
    obj_id = data['id']
    sid = request.sid
    if obj_id in object_selected_by and object_selected_by[obj_id] == sid:
        del object_selected_by[obj_id]
        emit('object_deselected', {'id': obj_id}, broadcast=True)
@socketio.on('disconnect')
def handle_disconnect():
    # 切断時にそのユーザーが選択していたものを解除
    sid = request.sid
    to_remove = [oid for oid, s in object_selected_by.items() if s == sid]
    for oid in to_remove:
        del object_selected_by[oid]
        emit('object_deselected', {'id': oid}, broadcast=True)


# --- プロジェクト保存API ---

@app.route('/api/save_project', methods=['POST'])
def api_save_project():
    data = request.get_json()
    name = data.get('name')
    objects_dict = data.get('objects')
    if not name or objects_dict is None:
        return jsonify({'success': False, 'error': 'name/objects required'}), 400
    result = ProjectDB.save(name, objects_dict)
    return jsonify({'success': result})

# --- プロジェクト読込API ---

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
    # 現在の全オブジェクト情報を新規クライアントに送信
    emit('init_objects', list(objects.values()))

@socketio.on('add_object')
def handle_add_object(data):
    global object_id_counter
    obj = {
        'id': object_id_counter,
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
    objects[object_id_counter] = obj
    object_id_counter += 1
    emit('add_object', obj, broadcast=True)


# --- 追加: 回転・スケール・全体同期イベント ---
@socketio.on('move_object')
def handle_move_object(data):
    obj_id = data['id']
    if obj_id in objects:
        objects[obj_id]['position'] = data['position']
        # 既存のrotation/scaleも送る
        emit('move_object', {
            **objects[obj_id],
        }, broadcast=True, include_self=False)

@socketio.on('rotate_object')
def handle_rotate_object(data):
    obj_id = data['id']
    rotation = data['rotation']
    if obj_id in objects:
        objects[obj_id]['rotation'] = rotation
        emit('rotate_object', {
            **objects[obj_id],
        }, broadcast=True, include_self=False)

@socketio.on('scale_object')
def handle_scale_object(data):
    obj_id = data['id']
    scale = data['scale']
    if obj_id in objects:
        objects[obj_id]['scale'] = scale
        emit('scale_object', {
            **objects[obj_id],
        }, broadcast=True, include_self=False)

if __name__ == '__main__':
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        webbrowser.open('http://localhost:5000/')
    socketio.run(app, host="0.0.0.0", debug=True)