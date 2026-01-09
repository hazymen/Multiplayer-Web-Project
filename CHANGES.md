# 実装変更内容

## 要件変更の実装概要

### 1. サイトアクセス時の部屋選択機能
- サイト起動時に、保存済みプロジェクトの一覧から入室する部屋を選択するダイアログを表示
- 初期状態では全てのThree.js機能は無効（レンダラー未初期化）
- 部屋を選択して「入室」ボタンを押すと、Three.js初期化とメインUIが表示される

### 2. 部屋（Room）の概念導入
- 各プロジェクトを「部屋」として認識
- Socket.IOのルーム機能を使用して、同じ部屋内でのみ通信を行う

### 3. ルーム内での編集共有
- 同じ部屋に参加しているクライアント同士のみが、編集内容をリアルタイムで共有
- 他の部屋のクライアントには操作が見えない

## 技術実装詳細

### フロントエンド（index.html）

#### 主な変更点：

1. **部屋選択モーダル**
   ```html
   <div id="room-selection-modal">
       <!-- 保存済みプロジェクト一覧から選択 -->
   </div>
   ```

2. **遅延初期化**
   - `startThreeJsRendering()` : 部屋選択後にThree.jsを初期化
   - `setupSocketAndEvents()` : Socket.IOイベントリスナーをセットアップ

3. **Socket.IO接続フロー**
   ```javascript
   // 1. ページロード時は部屋選択待ち
   // 2. 部屋選択後、socket.emit('join_room', {room_name: currentRoom})
   // 3. バックエンドで処理
   // 4. init_objectsイベント受信で、部屋内のオブジェクト初期化
   ```

### バックエンド（app.py）

#### 主な変更点：

1. **ルーム単位のデータ管理**
   ```python
   room_objects = {}              # {room_name: {obj_id: obj}}
   room_id_counter = {}           # {room_name: counter}
   room_object_selected_by = {}   # {room_name: {obj_id: sid}}
   client_rooms = {}              # {sid: room_name}
   ```

2. **join_roomハンドラ**
   - クライアントが部屋に参加時に呼ばれる
   - 既に別の部屋に参加していたら、そこから退出
   - 部屋内のオブジェクト情報をクライアントに送信

3. **ルーム指定emit**
   - すべてのSocket.IOイベント送信時に `room=room_name` を指定
   - 例：`emit('add_object', obj, room=room)`
   - これにより、同じ部屋内のクライアントのみがメッセージを受信

4. **接続・切断管理**
   - `connect`: 部屋参加待ち状態
   - `disconnect`: 部屋内の選択状態をクリア、client_roomsから削除

## 実装されたSocket.IOイベント（ルーム対応）

### クライアント → サーバー
- `join_room`: 部屋参加
- `add_object`: オブジェクト追加
- `move_object`: オブジェクト移動
- `rotate_object`: オブジェクト回転
- `scale_object`: オブジェクトスケール
- `delete_object`: オブジェクト削除
- `select_object`: オブジェクト選択
- `deselect_object`: オブジェクト選択解除
- `edit_face`: 面編集

### サーバー → クライアント（ルーム配信）
- `init_objects`: 初期オブジェクト情報
- `add_object`: オブジェクト追加通知
- `move_object`: オブジェクト移動通知
- `rotate_object`: オブジェクト回転通知
- `scale_object`: オブジェクトスケール通知
- `object_deleted`: オブジェクト削除通知
- `object_selected`: オブジェクト選択通知
- `object_deselected`: オブジェクト選択解除通知
- `edit_face`: 面編集通知

## 使用方法

1. アプリケーション起動
2. ブラウザでhttp://localhost:5000にアクセス
3. 部屋選択ダイアログで入室するプロジェクトを選択
4. 「入室」ボタンをクリック
5. メインUIが表示され、3D編集開始

複数クライアントが同じ部屋を選択すると、編集がリアルタイムで共有されます。

## 注意事項

- データベース接続が必要です（db_config.py参照）
- 部屋情報はサーバーメモリ上で管理されるため、サーバー再起動時には失われます
- 永続化が必要な場合は、定期的にプロジェクト保存機能を使用してください
