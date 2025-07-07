
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import webbrowser
import os

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

@socketio.on('edit_vertex')
def handle_edit_vertex(data):
    obj_id = data['id']
    idx = data['vertex_index']
    position = data['position']
    # サーバー側では頂点情報は保持しないが、全クライアントへブロードキャスト
    emit('edit_vertex', {
        'id': obj_id,
        'vertex_index': idx,
        'position': position
    }, broadcast=True)
    
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
        'color': data.get('color', None)
    }
    objects[object_id_counter] = obj
    object_id_counter += 1
    emit('add_object', obj, broadcast=True)

@socketio.on('move_object')
def handle_move_object(data):
    obj_id = data['id']
    if obj_id in objects:
        objects[obj_id]['position'] = data['position']
        emit('move_object', data, broadcast=True)

if __name__ == '__main__':
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        webbrowser.open('http://localhost:5000/')
    socketio.run(app, host="0.0.0.0", debug=True)