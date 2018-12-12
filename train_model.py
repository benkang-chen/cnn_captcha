# -*- coding: utf-8 -*-
import tensorflow as tf
import numpy as np
import matplotlib.pyplot as plt
import time
from PIL import Image
import random
import os
from sample import sample_conf
from tensorflow.python.framework.errors_impl import NotFoundError

# 设置以下环境变量可开启CPU识别
# os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
# os.environ["CUDA_VISIBLE_DEVICES"] = "-1"


class TrainError(Exception):
    pass


class TrainModel(object):
    def __init__(self, img_path, char_set, model_save_dir, verify=False):
        # 模型路径
        self.model_save_dir = model_save_dir

        # 打乱文件顺序+校验图片格式
        self.img_path = img_path
        self.img_list = os.listdir(img_path)
        # 校验格式
        if verify:
            self.confirm_image_suffix()
        # 打乱文件顺序
        random.seed(time.time())
        random.shuffle(self.img_list)

        # 获得图片宽高和字符长度基本信息
        label, captcha_array = self.gen_captcha_text_image(self.img_list[0])

        captcha_shape = captcha_array.shape
        captcha_shape_len = len(captcha_shape)
        if captcha_shape_len == 3:
            image_height, image_width, channel = captcha_shape
            self.channel = channel
        elif captcha_shape_len == 2:
            image_height, image_width = captcha_shape
        else:
            raise TrainError("图片转换为矩阵时出错，请检查图片格式")

        # 初始化变量
        # 图片尺寸
        self.image_height = image_height
        self.image_width = image_width
        # 验证码长度（位数）
        self.max_captcha = len(label)
        # 验证码字符类别
        self.char_set = char_set
        self.char_set_len = len(char_set)

        # 相关信息打印
        print("-->图片尺寸: {} X {}".format(image_height, image_width))
        print("-->验证码长度: {}".format(self.max_captcha))
        print("-->验证码共{}类 {}".format(self.char_set_len, char_set))
        print("-->使用测试集为 {}".format(img_path))

        # tf初始化占位符 [None, 3]表示列是3，行不定
        self.X = tf.placeholder(tf.float32, [None, image_height * image_width])  # 特征向量
        self.Y = tf.placeholder(tf.float32, [None, self.max_captcha * self.char_set_len])  # 标签
        self.keep_prob = tf.placeholder(tf.float32)  # dropout值
        self.w_alpha = 0.01
        self.b_alpha = 0.1

        # test model input and output
        print(">>> Start model test")
        batch_x, batch_y = self.get_batch(0, size=100)
        print(">>> input batch images shape: {}".format(batch_x.shape))
        print(">>> input batch labels shape: {}".format(batch_y.shape))

    def gen_captcha_text_image(self, img_name):
        """
        返回一个验证码的array形式和对应的字符串标签
        :return:tuple (str, numpy.array)
        """
        # 标签
        label = img_name.split("_")[0]
        # 文件
        img_file = os.path.join(self.img_path, img_name)
        captcha_image = Image.open(img_file)
        captcha_array = np.array(captcha_image)  # 向量化
        return label, captcha_array

    @staticmethod
    def convert2gray(img):
        """
        图片转为灰度图，如果是3通道图则计算，单通道图则直接返回
        :param img:
        :return:
        """
        if len(img.shape) > 2:
            r, g, b = img[:, :, 0], img[:, :, 1], img[:, :, 2]
            gray = 0.2989 * r + 0.5870 * g + 0.1140 * b
            return gray
        else:
            return img

    def text2vec(self, text):
        """
        转标签为oneHot编码
        :param text: str
        :return: numpy.array
        """
        text_len = len(text)
        if text_len > self.max_captcha:
            raise ValueError('验证码最长{}个字符'.format(self.max_captcha))

        vector = np.zeros(self.max_captcha * self.char_set_len)

        for i, ch in enumerate(text):
            idx = i * self.char_set_len + self.char_set.index(ch)
            vector[idx] = 1
        return vector

    def get_batch(self, n, size=128):
        batch_x = np.zeros([size, self.image_height * self.image_width])  # 初始化
        batch_y = np.zeros([size, self.max_captcha * self.char_set_len])  # 初始化

        max_batch = int(len(self.img_list) / size)
        # print(max_batch)
        if max_batch - 1 < 0:
            raise TrainError("训练集图片数量需要大于每批次训练的图片数量")
        if n > max_batch - 1:
            n = n % max_batch
        s = n * size
        e = (n + 1) * size
        this_batch = self.img_list[s:e]
        # print("{}:{}".format(s, e))

        for i, img_name in enumerate(this_batch):
            label, image_array = self.gen_captcha_text_image(img_name)
            image_array = self.convert2gray(image_array)  # 灰度化图片
            batch_x[i, :] = image_array.flatten() / 255  # flatten 转为一维
            batch_y[i, :] = self.text2vec(label)  # 生成 oneHot
        return batch_x, batch_y

    def confirm_image_suffix(self):
        # 在训练前校验所有文件格式
        print("开始校验所有图片后缀")
        for index, img_name in enumerate(self.img_list):
            print("{} image pass".format(index), end='\r')
            if not img_name.endswith(sample_conf['image_suffix']):
                raise TrainError('confirm images suffix：you request [.{}] file but get file [{}]'
                                 .format(sample_conf['image_suffix'], img_name))
        print("所有图片格式校验通过")

    def model(self):
        # -1 表示自动推断的维度
        x = tf.reshape(self.X, shape=[-1, self.image_height, self.image_width, 1])
        print(">>> input x: {}".format(x))
        # 卷积层1
        # tf.get_variable 获取已存在的变量（要求不仅名字，而且初始化方法等各个参数都一样），如果不存在，就新建一个。
        # 可以用各种初始化方法，不用明确指定值。
        # tf.contrib.layers.xavier_initializer 该函数返回一个用于初始化权重的初始化程序 “Xavier” 。
        # 这个初始化器是用来保持每一层的梯度大小都差不多相同。返回值：初始化权重矩阵
        wc1 = tf.get_variable(name='wc1', shape=[3, 3, 1, 32], dtype=tf.float32,
                              initializer=tf.contrib.layers.xavier_initializer())
        # 初始化偏差项
        bc1 = tf.Variable(self.b_alpha * tf.random_normal([32]))
        # tf.nn.conv2d(input, filter, strides, padding, use_cudnn_on_gpu=None, name=None)
        # 1.第一个参数input：指需要做卷积的输入图像，它要求是一个Tensor，具有[batch, in_height, in_width, in_channels]
        #   这样的shape，具体含义是[训练时一个batch的图片数量, 图片高度, 图片宽度, 图像通道数]，注意这是一个4维的Tensor，
        #   要求类型为float32和float64其中之一
        # 2.第二个参数filter：相当于CNN中的卷积核，它要求是一个Tensor，
        #   具有[filter_height, filter_width, in_channels, out_channels]这样的shape，
        #   具体含义是[卷积核的高度，卷积核的宽度，图像通道数，卷积核个数]，要求类型与参数input相同，有一个地方需要注意，
        #   第三维in_channels，就是参数input的第四维
        # 3.第三个参数strides：卷积时在图像每一维的步长，这是一个一维的向量，长度4
        # 4.第四个参数padding：string类型的量，只能是"SAME","VALID"其中之一，这个值决定了不同的卷积方式,当其为‘SAME’时，
        #   表示卷积核可以停留在图像边缘
        # 5.第五个参数：use_cudnn_on_gpu:bool类型，是否使用cudnn加速，默认为true
        # 结果返回一个Tensor，这个输出，就是我们常说的feature map
        conv1 = tf.nn.relu(tf.nn.bias_add(tf.nn.conv2d(x, wc1, strides=[1, 1, 1, 1], padding='SAME'), bc1))
        # tf.nn.max_pool
        # 第一个参数value：需要池化的输入，一般池化层接在卷积层后面，所以输入通常是feature map，
        # 依然是[batch, height, width, channels]这样的shape
        #
        # 第二个参数ksize：池化窗口的大小，取一个四维向量，一般是[1, height, width, 1]，
        # 因为我们不想在batch和channels上做池化，所以这两个维度设为了1
        #
        # 第三个参数strides：和卷积类似，窗口在每一个维度上滑动的步长，一般也是[1, stride,stride, 1]
        #
        # 第四个参数padding：和卷积类似，可以取'VALID' 或者'SAME'
        conv1 = tf.nn.max_pool(conv1, ksize=[1, 2, 2, 1], strides=[1, 2, 2, 1], padding='SAME')
        # tf.nn.dropout是TensorFlow里面为了防止或减轻过拟合而使用的函数，它一般用在全连接层。
        #
        # Dropout就是在不同的训练过程中随机扔掉一部分神经元。也就是让某个神经元的激活值以一定的概率p，让其停止工作，
        # 这次训练过程中不更新权值，也不参加神经网络的计算。但是它的权重得保留下来（只是暂时不更新而已）
        # 因为下次样本输入时它可能又得工作了。
        x_shape = x.shape.as_list()
        if x_shape[0] is None:
            x_shape[0] = 100
        deconv = tf.nn.conv2d_transpose(conv1, wc1, x_shape, strides=[1, 2, 2, 1], padding='SAME')
        tf.summary.image('conv1_out', deconv, 10)
        conv1 = tf.nn.dropout(conv1, self.keep_prob)
        conv1_shape = conv1.shape.as_list()
        if conv1_shape[0] is None:
            conv1_shape[0] = 100
        tf.summary.histogram('conv1/wc1', wc1)
        tf.summary.histogram('conv1/bc1', bc1)
        # 卷积层2
        wc2 = tf.get_variable(name='wc2', shape=[3, 3, 32, 64], dtype=tf.float32,
                              initializer=tf.contrib.layers.xavier_initializer())
        bc2 = tf.Variable(self.b_alpha * tf.random_normal([64]))
        conv2 = tf.nn.relu(tf.nn.bias_add(tf.nn.conv2d(conv1, wc2, strides=[1, 1, 1, 1], padding='SAME'), bc2))
        conv2 = tf.nn.max_pool(conv2, ksize=[1, 2, 2, 1], strides=[1, 2, 2, 1], padding='SAME')
        deconv2 = tf.nn.conv2d_transpose(conv2, wc2, conv1_shape, strides=[1, 2, 2, 1], padding='SAME')
        deconv2_ = tf.nn.conv2d_transpose(deconv2, wc1, x_shape, strides=[1, 2, 2, 1], padding='SAME')
        tf.summary.image('conv2_out', deconv2_, 10)
        conv2 = tf.nn.dropout(conv2, self.keep_prob)
        conv2_shape = conv2.shape.as_list()
        if conv2_shape[0] is None:
            conv2_shape[0] = 100
        tf.summary.histogram('conv2/wc2', wc2)
        tf.summary.histogram('conv2/bc2', bc2)
        # 卷积层3
        wc3 = tf.get_variable(name='wc3', shape=[3, 3, 64, 128], dtype=tf.float32,
                              initializer=tf.contrib.layers.xavier_initializer())
        bc3 = tf.Variable(self.b_alpha * tf.random_normal([128]))
        conv3 = tf.nn.relu(tf.nn.bias_add(tf.nn.conv2d(conv2, wc3, strides=[1, 1, 1, 1], padding='SAME'), bc3))
        conv3 = tf.nn.max_pool(conv3, ksize=[1, 2, 2, 1], strides=[1, 2, 2, 1], padding='SAME')

        deconv3 = tf.nn.conv2d_transpose(conv3, wc3, conv2_shape, strides=[1, 2, 2, 1], padding='SAME')
        deconv3_ = tf.nn.conv2d_transpose(deconv3, wc2, conv1_shape, strides=[1, 2, 2, 1], padding='SAME')
        deconv3__ = tf.nn.conv2d_transpose(deconv3_, wc1, x_shape, strides=[1, 2, 2, 1], padding='SAME')
        tf.summary.image('conv3_out', deconv3__, 10)
        conv3 = tf.nn.dropout(conv3, self.keep_prob)
        tf.summary.histogram('conv3/wc3', wc3)
        tf.summary.histogram('conv3/bc3', bc3)
        print(">>> convolution 3: ", conv3.shape)
        next_shape = conv3.shape[1] * conv3.shape[2] * conv3.shape[3]

        # 全连接层1
        wd1 = tf.get_variable(name='wd1', shape=[next_shape, 1024], dtype=tf.float32,
                              initializer=tf.contrib.layers.xavier_initializer())
        bd1 = tf.Variable(self.b_alpha * tf.random_normal([1024]))
        dense = tf.reshape(conv3, [-1, wd1.get_shape().as_list()[0]])
        dense = tf.nn.relu(tf.add(tf.matmul(dense, wd1), bd1))
        dense = tf.nn.dropout(dense, self.keep_prob)

        # 全连接层2
        wout = tf.get_variable('name', shape=[1024, self.max_captcha * self.char_set_len], dtype=tf.float32,
                               initializer=tf.contrib.layers.xavier_initializer())
        bout = tf.Variable(self.b_alpha * tf.random_normal([self.max_captcha * self.char_set_len]))
        y_predict = tf.add(tf.matmul(dense, wout), bout)
        return y_predict

    def train_cnn(self):
        y_predict = self.model()
        print(">>> input batch predict shape: {}".format(y_predict.shape))
        print(">>> End model test")
        # 计算概率 损失
        cost = tf.reduce_mean(tf.nn.sigmoid_cross_entropy_with_logits(logits=y_predict, labels=self.Y))
        tf.summary.scalar('loss', cost)
        # 梯度下降
        optimizer = tf.train.AdamOptimizer(learning_rate=0.0001).minimize(cost)
        # 计算准确率
        predict = tf.reshape(y_predict, [-1, self.max_captcha, self.char_set_len])  # 预测结果
        max_idx_p = tf.argmax(predict, 2)  # 预测结果
        max_idx_l = tf.argmax(tf.reshape(self.Y, [-1, self.max_captcha, self.char_set_len]), 2)  # 标签
        # 计算准确率
        correct_pred = tf.equal(max_idx_p, max_idx_l)
        accuracy = tf.reduce_mean(tf.cast(correct_pred, tf.float32))
        tf.summary.scalar('acc', accuracy)
        # 模型保存对象
        saver = tf.train.Saver()
        with tf.Session() as sess:
            init = tf.global_variables_initializer()
            merged = tf.summary.merge_all()
            sess.run(init)
            writer = tf.summary.FileWriter(logdir="./logs", graph=sess.graph)
            # 恢复模型
            if os.path.exists(self.model_save_dir):
                try:
                    saver.restore(sess, self.model_save_dir)
                # 判断捕获model文件夹中没有模型文件的错误
                except NotFoundError:
                    print("model文件夹为空，将创建新模型")
            else:
                pass
            step = 1
            for i in range(6000):
                batch_x, batch_y = self.get_batch(i, size=128)
                _, cost_ = sess.run([optimizer, cost], feed_dict={self.X: batch_x, self.Y: batch_y, self.keep_prob: 0.75})
                # writer.add_summary(tf.Summary(value=[tf.Summary.Value(tag="loss", simple_value=cost_)]), global_step=i)
                if step % 10 == 0:
                    batch_x_test, batch_y_test = self.get_batch(i, size=100)
                    res = sess.run(merged, feed_dict={self.X: batch_x_test, self.Y: batch_y_test, self.keep_prob: 1.})
                    acc = sess.run(accuracy, feed_dict={self.X: batch_x_test, self.Y: batch_y_test, self.keep_prob: 1.})
                    writer.add_summary(res, i)
                    print("第{}次训练 >>> 准确率为 {} >>> loss {}".format(step, acc, cost_))
                    # 准确率达到99%后保存并停止
                    if acc > 0.99:
                        saver.save(sess, self.model_save_dir)
                        break
                # 每训练500轮就保存一次
                if i % 500 == 0:
                    saver.save(sess, self.model_save_dir)
                step += 1
            saver.save(sess, self.model_save_dir)
            writer.close()

    def recognize_captcha(self):
        label, captcha_array = self.gen_captcha_text_image(random.choice(self.img_list))

        f = plt.figure()
        ax = f.add_subplot(111)
        ax.text(0.1, 0.9, "origin:" + label, ha='center', va='center', transform=ax.transAxes)
        plt.imshow(captcha_array)
        # 预测图片
        image = self.convert2gray(captcha_array)
        image = image.flatten() / 255

        y_predict = self.model()

        saver = tf.train.Saver()
        with tf.Session() as sess:
            saver.restore(sess, self.model_save_dir)
            predict = tf.argmax(tf.reshape(y_predict, [-1, self.max_captcha, self.char_set_len]), 2)
            text_list = sess.run(predict, feed_dict={self.X: [image], self.keep_prob: 1.})
            predict_text = text_list[0].tolist()

        print("正确: {}  预测: {}".format(label, predict_text))
        # 显示图片和预测结果
        p_text = ""
        for p in predict_text:
            p_text += str(self.char_set[p])
        print(p_text)
        plt.text(20, 1, 'predict:{}'.format(p_text))
        plt.show()


def main():
    train_image_dir = sample_conf["train_image_dir"]
    char_set = sample_conf["char_set"]
    model_save_dir = sample_conf["model_save_dir"]
    tm = TrainModel(train_image_dir, char_set, model_save_dir, verify=False)
    tm.train_cnn()  # 开始训练模型
    # tm.recognize_captcha()  # 识别图片示例


if __name__ == '__main__':
    main()
